# H7 — TIME OF DAY (entry-time-bucket outcome study + later-entry-gate costing)

**Stamp:** 2026-09-03T10:24 ET (registered by orchestrator). Runner fired ~10:42-10:55 ET same
session (`et_clock.py`: `2026-09-03 10:42:31 Thursday EDT`, `market_hours=True`).
**Runner:** `backtest/tools/money_time_of_day.py`. **Raw:** `analysis/deep-research/2026-09-03-money/time-of-day.json`.
**Read-only session** — no broker/market-data calls, no writes to `automation/state/**` or
`journal/**`. Population is 100% cached, already-computed data.

---

## VERDICT: REFUTED as an actionable gate. NONE ships.

Every one of the 3 candidate later-entry gates (09:45 / 09:50 / 10:00) either **worsens the
book** or **cannibalizes 48-114% of a named winning day's P&L** — because the two winning days
that have any early activity (08-13, 08-27) get their single biggest wave of the day from a
**09:41-09:52 simultaneous multi-arm entry**. There is no clean line to draw. Day-level
bootstrap CIs (the correct unit here — see "Independence" below) cross zero in **all 5**
time-of-day buckets. The two buckets that look bad on a trade-count basis are each a
**single-day artifact**.

A real, separate, smaller finding survives: entries in 09:35-09:50 do show the engine's
structure classifier reporting `unknown:insufficient_bars` far more often than later entries —
but that evidence is n=10 and only exists from 2026-08-19 onward. It's a plausible mechanism,
not a validated gate.

**Ships:** nothing. Config freeze is in force to 2026-10-30 regardless (work-order §0); this
report is filed as evidence for that menu, matching the pattern already set by
`analysis/recommendations/prereg-hour-gate-12xx-2026-09-02.json` (measure now, decide at the
freeze's end).

---

## 1. Population

- **Source:** `analysis/pain-ledger/mae-mfe.json` `trades[]` — broker-fills-derived,
  `attribution==engine`, real OPRA 1-min bars for MAE/MFE (not used here beyond provenance).
  This is the cleanest available "all engine fills" population and matches the task's
  instrument list.
- **n = 368** scored trades, **2026-07-01 → 2026-09-02**, across all 6 live arms
  (safe-2, bold-2, safe-3, safe-1, risky-1, risky-3).
- Arms: `{"safe-2": 88, "risky-3": 87, "risky-1": 76, "safe-3": 56, "bold-2": 41, "safe-1": 20}`.
- Setups: `BULLISH_RECLAIM_RIDE_THE_RIBBON` 195, `BEARISH_REJECTION_RIDE_THE_RIBBON` 94,
  `VWAP_CONTINUATION` 41, `(unattributed)` 35, `VWAP_RECLAIM_FAILED_BREAK` 3.
- **4 excluded-from-nothing anomaly rows**: 2026-07-02 has 4 fills at 09:30-09:31 ET, before the
  documented 09:35 gate — pre-dates the window this study buckets (excluded from all 5 named
  buckets, reported here only). Not investigated further; too old (day 2 of the current era) to
  be actionable, flagged for completeness per "name every excluded row."

**Independence — the reason every stat below is reported two ways.** The fleet's shared-signal
architecture (`automation/state/fleet/build_shared_signal.py`) fires the **same** setup across
up to 6 arms within the same 1-2 minutes. A naive per-trade n treats those as 6 independent
trials; they are 1 trading decision replicated 6x at different position sizes. Every table below
is reported at **trade-level** (n=368) **and** **day-level** (PnL summed per distinct trading
day within the bucket, n=9-27) — the day-level number is the one to trust for "is this bucket
really different."

---

## 2. Outcome by entry-time bucket

| Bucket | n trades | n days | total $ | trade mean $ (95% CI) | day mean $ (95% CI) | day win-rate | PF (trade, 95% CI) |
|---|--:|--:|--:|---|---|--:|---|
| 09:35-09:50 | 31 | 9 | **-$1,303** | -$42.03 [-107.61, 26.19] | -$144.78 [-605.00, 262.44] | 33.3% (3/9) | 0.556 [0.172, 1.366] |
| 09:50-10:30 | 103 | 20 | +$1,760 | +$17.09 [-21.27, 58.91] | +$88.00 [-294.05, 513.15] | 25.0% (5/20) | 1.302 [0.673, 2.196] |
| 10:30-12:00 | 79 | 19 | +$50 | +$0.63 [-39.70, 43.86] | +$2.63 [-206.11, 264.47] | 26.3% (5/19) | 1.010 [0.472, 1.932] |
| 12:00-14:00 | 104 | 27 | **-$1,468** | -$14.12 [-47.32, 21.63] | -$54.37 [-294.63, 201.15] | 33.3% (9/27) | 0.776 [0.369, 1.418] |
| 14:00-15:20 | 47 | 18 | **+$2,286** | +$48.64 [+13.32, +86.43] | +$127.00 [-0.39, +285.06] | 44.4% (8/18) | 3.613 [1.565, 8.494] |

Bootstrap: 3,000 resamples, percentile CI (2.5%/97.5%), seeded (42) for reproducibility.

**Reading this table honestly:** at the trade level, the CI on mean $ **crosses zero for all 5
buckets**. At the day level (the correct independence unit), it **also crosses zero for all 5**
— including 14:00-15:20, whose lower bound is -$0.39, a hair's-breadth miss. Two buckets have a
negative point-estimate total (09:35-09:50, 12:00-14:00); neither is distinguishable from noise
at n=9 and n=27 days respectively, and both dissolve on inspection (§3).

---

## 3. The two "bad" buckets are single-day artifacts

### 09:35-09:50 (bucket A)

9 distinct days fired an entry in this window (all `BULLISH_RECLAIM_RIDE_THE_RIBBON` or
`VWAP_CONTINUATION` — **zero** `BEARISH_REJECTION` entries land this early; bear needs
`min_triggers>=1` vs bull `>=1` too per params but bear's structure/ribbon-stack requirement
takes longer to confirm — consistent with the `winner_day_entry_blockers.md` F5/F6 finding that
ribbon warmup takes ~20-40 min after the open).

| date | day $ | n | note |
|---|--:|--:|---|
| 2026-07-09 | -$182 | 4 | |
| 2026-08-03 | +$466 | 3 | |
| 2026-08-04 | -$179 | 2 | |
| 2026-08-07 | -$628 | 4 | |
| 2026-08-10 | -$120 | 3 | |
| 2026-08-11 | +$90 | 1 | |
| 2026-08-12 | -$119 | 2 | |
| **2026-08-14** | **-$1,569** | **5** | **worst day — 5 correlated `BULLISH_RECLAIM` losers, one shared signal fired across bold-2/risky-1/risky-3/safe-2/safe-3 at 09:46-09:47** |
| 2026-08-27 | +$938 | 7 | winning day (see §4) |

**Remove the single worst day (08-14) and the bucket total flips from -$1,303 to +$266.** One
correlated multi-arm loss, not a persistent time-of-day effect, explains the entire negative
sign of this bucket.

### 12:00-14:00 (bucket D)

27 distinct days, much broader spread — but still dominated by one day:

- **2026-08-07: -$2,020** (7 trades) — bucket total ex-that-day = **+$552** (from -$1,468).
- This is a **different** day than the one already frozen for the noon hour in
  `analysis/recommendations/prereg-hour-gate-12xx-2026-09-02.json` (that study measured the
  `12:xx` **hour** specifically across the full history and found it the single most
  consistently negative hour in both eras — **cited, not re-run here**; my 12:00-14:00 bucket is
  a wider 2-hour window that includes 13:xx, so the two studies are not measuring the same
  slice and should not be read as confirming or contradicting each other without re-slicing).
  The 2026-10-30 shape-change menu already has that noon-hour candidate frozen and pending; this
  report does not add a second, overlapping midday candidate — see recommendation in §7.

---

## 4. Winning-day check — does a later-entry gate cost the wins it's supposed to protect?

Per the task's four flagship winning days:

| day | day total | entries before 09:45 | entries before 09:50 | entries before 10:00 |
|---|--:|---|---|---|
| 2026-08-06 | +$1,465 | none | none | none |
| 2026-08-13 | +$1,748 | none | none | **5 trades, +$1,985 (114% of day total)** |
| 2026-08-27 | +$1,897 | 5 trades, +$1,078 (57%) | 7 trades, +$938 (49%) | 7 trades, +$938 (49%) |
| 2026-08-28 | +$1,304 | none | none | none |

08-06 and 08-28 are untouched by any candidate gate — their entries all land at 10:30+.
**08-13 and 08-27 are not.** Both days' **single biggest wave** is a simultaneous multi-arm
entry into the same `BULLISH_RECLAIM_RIDE_THE_RIBBON` trigger, fired 09:41-09:52:

- **2026-08-13**: safe-2/bold-2/safe-3/risky-1/risky-3 all enter 09:51-09:52, **+$1,985**
  combined. Every subsequent trade that day nets to **-$237** (10:27 loser, 11:41-11:42 four
  losers, 12:41 two losers, 14:36-14:37 three winners +$532). **Without the 09:51-09:52 wave,
  2026-08-13 is a LOSING day (-$237), not a winning one.** A 10:00 gate does not trim this day's
  edge — it deletes the day's entire edge.
- **2026-08-27**: the same five arms enter 09:41-09:42, **+$1,078** combined, then two
  smaller losers at 09:47-09:48 (-$140), then a second wave at 11:52-11:53 (+$775), then one
  more winner at 12:31 (+$184). A 09:45/09:50/10:00 gate removes roughly half the day's total.

---

## 5. Gate costing — 09:45 / 09:50 / 10:00

| gate | removed n (trade) | removed cohort $ | removed cohort WR | book delta if gated | 08-13 blocked | 08-27 blocked |
|---|--:|--:|--:|--:|---|---|
| **09:45** | 19 | **+$991** (WR 42.1%) | positive | **-$991 (worse)** | $0 | $1,078 (57%) |
| **09:50** | 31 | -$1,554 (WR 25.7%) | negative | **+$1,554 (better)** | $0 | $938 (49%) |
| **10:00** | 88 | **+$191** (WR 27.3%) | positive | **-$191 (worse)** | **$1,985 (114%)** | $938 (49%) |

- **09:45 REJECT** — the cohort it removes (09:35-09:44) is itself net **positive** (+$991,
  WR 42.1% — well above the population baseline WR ~27%). Gating it makes the book worse and
  costs over half of 08-27.
- **10:00 REJECT** — worse on both counts: makes the book worse (-$191) *and* deletes more
  than the entirety of 08-13's edge, *and* half of 08-27's.
- **09:50** is the only candidate that improves the raw book (+$1,554), because it is the one
  gate that happens to land exactly between the 09:41-09:48 losing tail and the 09:51-09:52
  winning wave on 08-13 (lucky boundary, not a designed one) — but it still deletes **49% of
  2026-08-27's P&L**, one of the four days this project treats as proof the edge works. A gate
  that keeps the book number but guts a flagship winning day is not a clean win; it is a
  trade J would have to explicitly bless knowing it would have halved 08-27.

**No candidate clears "helps the book AND doesn't touch a winning day."** None is recommended.

---

## 6. structure_reason / range_position sub-finding (schema-limited)

`conviction.structure_reason` and `conviction.components.range_position` only exist on the
core (safe/bold) decision path (`automation/state/core-decisions.jsonl`) from **2026-08-19**
onward — **absent** on all 4 fleet arms (safe-1/safe-3/risky-1/risky-3) at every date, and
absent on the core path before 08-19. This sub-check is therefore a much smaller, later,
narrower population than §2-5 above.

| | n PLACED | `structure_reason == unknown:insufficient_bars` |
|---|--:|---|
| 09:35-09:49 ET | 10 | **5 (50%)** |
| 09:50+ ET | 86 | 2 (2.3%) |

The `range_position` values that DO exist for the early window are extreme (0.64, 0.64, 1.0,
0.966, 0.966 — near the top of the day's range so far, consistent with the book-wide "extreme
range_position on losers" observation in this session's brief) but **5 of 10 early rows have no
`range_position` at all** (component simply absent — the classifier hadn't produced one yet),
which is itself the "meaningless range_position" the hypothesis named.

**This is a real, plausible mechanism** — the bull trigger fires on a lower bar-count threshold
than bear (per `params.json` bull `min_triggers>=1` vs bear's stricter confirmation), so it can
fire before the structure classifier has enough bars to say anything — **but n=10 is far below
any usable bar**, and it cannot be extended further back because the field didn't exist before
08-19. It is filed as a mechanism candidate, not a gate.

---

## 7. Regime interaction (VIX, disclosed per bucket)

VIX read via nearest-prior-tick asof join from `core-decisions.jsonl` (account=safe, market-
level value, no look-ahead — reading is always at-or-before the trade's entry tick).

| bucket | <15 VIX | 15-17 VIX | >17 VIX |
|---|---|---|---|
| 09:35-09:50 | n=7, **-$1,688**, WR 0% | n=24, +$385, WR 37.5% | (none) |
| 09:50-10:30 | n=32, +$3,229, WR 43.8% | n=48, -$44, WR 16.7% | n=23, **-$1,425**, WR 13.0% |
| 10:30-12:00 | n=13, +$305, WR 38.5% | n=55, +$810, WR 25.5% | n=11, **-$1,065**, WR 9.1% |
| 12:00-14:00 | n=26, **-$3,107**, WR 11.5% | n=64, +$1,586, WR 31.2% | n=14, +$53, WR 42.9% |
| 14:00-15:20 | n=6, +$660, WR 83.3% | n=33, +$477, WR 24.2% | n=8, +$1,149, WR 50.0% |

**VIX regime is not a clean discriminator either** — `<15` is catastrophic in bucket A (WR 0%,
all 7 trades are 2 of the 9 correlated-multi-arm days, 08-12 and 08-14 — the same worst-day
artifact from §3) and in bucket D, but strongly *positive* in buckets B and E. `>17` is
catastrophic in B and C but strongly positive in E. No single VIX cut travels across the whole
session — reinforces C5 (VIX *character*, not level, and here not even that travels cleanly
across time-of-day) rather than adding a new validated cut.

---

## 8. Existing 09:35 gate — provenance (cited, not re-derived)

`automation/state/params.json` (both `safe` and `aggressive`): `entry_no_trade_before_et:
"09:35"`, unchanged since **v15.1, 2026-05-14 evening**, J's own words quoted in the file:
*"any time between 9:35 - and 3pm is fair game for ENTRIES. theta will kill us after 3."* The
same file's history note records the prior 14:00-15:00 mid-day blackout was **removed** at the
same time — i.e. the last time this project tried a time-based entry restriction on doctrine
grounds, it was removed for costing real trades, not added.

## 9. Prior time-gate A/Bs (cited, not re-run)

- `analysis/recommendations/morning-gate-result.md` (2026-07-14) — 3 earlier-cutoff-style gates
  (11:00 / 10:30 / 10:35 first-hour) all **KILL** (fail stage1+stage2+BH-FDR) and all 3 block
  J's own OP-16 anchor winners (4/29, 5/04). Same shape of failure as this study's §4.
- `analysis/recommendations/safe_time_class_gate.json` /
  `analysis/recommendations/agg_time_class_gate.json` (2026-06-17) — time-of-day gates on a
  narrower trigger class (confluence+level_reclaim), not a blanket entry-time gate; the
  "afternoon only" cut for that specific class AUTO-RATIFIED (small, WF 2.2-2.6) but this never
  became a blanket 09:35-09:5x entry gate and is not evidence for one.
- `analysis/recommendations/prereg-hour-gate-12xx-2026-09-02.json` (yesterday, 2026-09-02) —
  the noon (12:xx) hour specifically is frozen as the single most consistent losing hour across
  both eras, **NOT a shipping decision**, parked for the 2026-10-30 menu. My 12:00-14:00 bucket
  overlaps this but is a wider window; do not merge the two without re-slicing on the same hour
  boundaries (see §3).
- `analysis/recommendations/ENTRY-LOCATION-GATE-2026-08-14.md` — a related entry-quality gate
  (proximity-to-level at entry) failed its own BH-FDR test at the one cell that looked
  significant uncorrected. Same genre of near-miss this study finds for 09:50 (§5).

---

## 10. What this changes

**Nothing ships.** `proposed_change: NONE`. Reasons, in order:

1. Day-level CIs cross zero in all 5 buckets — no bucket clears a statistical bar on its own.
2. The two negative-looking buckets are each explained by ONE anomalous correlated-multi-arm
   day, not a persistent time effect.
3. All 3 candidate gates fail the "helps the book AND doesn't gut a winning day" test — the
   best of the three (09:50) still costs 49% of 2026-08-27.
4. The one real mechanism finding (`structure_reason: unknown:insufficient_bars` concentrated
   early) is n=10 and schema-limited to the last 2 weeks — not powered for a decision.
5. Config freeze is in force to 2026-10-30 regardless (work-order §0) — nothing here would ship
   even if it had cleared the bars above.

This report is filed as one more input to the 2026-10-30 shape-change menu, alongside the
already-frozen noon-hour candidate. If a future session wants to pursue the structure-readiness
mechanism (§6) rather than a blanket time gate, the more surgical candidate worth pre-registering
then is a **structure-confirmation gate keyed to `structure_reason`/bar-count**, not a clock —
a clock cut demonstrably takes 08-13's and 08-27's best trade with it; a readiness cut might not,
but that is untested here and would need its own frozen pre-registration once n grows past 08-19.

---

## Caveats / what was not done

- No broker or market-data call was made (hard constraint); all figures are from cached
  `analysis/pain-ledger/mae-mfe.json`, `automation/state/core-decisions.jsonl`, and
  `automation/state/params.json`.
- MAE/MFE fields from the pain ledger were not used in this study beyond provenance —
  out of scope for a time-of-day question, and that ledger is explicitly "descriptive only,
  validates no stop change" (its own disclosure).
- `structure_reason`/`range_position` are UNVERIFIED as a population-wide signal — confirmed
  present only on the safe/bold core path from 2026-08-19, n=10 in the bucket of interest.
- VIX regime join is an asof (nearest-prior-tick) match against the `safe` account's tick
  stream, applied to all 6 arms as a market-level value (VIX is not account-specific) — this is
  a reasonable approximation, not a per-arm exact read.
- 2026-07-02's 4 pre-09:35 fills are reported (§1) but not investigated — old enough (day 2 of
  the tracked era) that root-causing them is out of scope for this pass.
- I did not attempt a structure-readiness-gate backtest (§10) — that is future work, explicitly
  not run here.
