# D8 — the two gates that refused Safe-2: full-population revalidation

Stamp: 2026-09-03T11:40 ET (report generated 2026-09-03T11:53 ET, market OPEN).
Slug: `gates-revalidation`. Runners: `backtest/tools/dissect_gates_revalidation.py` (Part A),
`backtest/tools/dissect_f10_bull_relax.py` (Part B). Raw output: `dissect-gates-revalidation-partA.json`,
`dissect-gates-revalidation-partB.json` (same directory).

**Both gates are EXPANSIONS under the 2026-10-30 config freeze — this report changes nothing in
params.json either way.** It answers only: does the live-ledger evidence since each gate's own
provenance date clear a bar that would justify expansion once the freeze lifts? For both gates,
**no.**

---

## Part A — `block_bull_1100_1200` (safe-only, params.json:215)

### The mechanism that already exists

`build_shared_signal.py`'s **probe arm** (fleet arm **risky-3**, `accounts.json` `probe_arm`
block) is the standing forward-probe this gate already has: it bypasses `SKIP_BULL_1100_1200`
specifically (the ONLY verdict on `PROBE_ALLOWED_VERDICTS`) at `min_contracts`, tagging fills
`reason="PROBE_ARM cohort=bull_1100_1200"`. No dedicated probe-count ledger has a nonzero entry
yet (`automation/state/fleet/risky-3/probe-count.json` does not exist on disk — **UNVERIFIED
whether the probe has ever actually fired**; the module comment's own worked example,
2026-08-13 11:41-11:43, shows safe-3/risky-1/risky-3 entering via the ordinary shared-signal
`passed_scoring_peak` rescue lane, not necessarily the probe lane specifically). The probe
mechanism and the ordinary "any arm with score>=peak(9)+trigger enters regardless of
production's verdict" rescue lane are BOTH why fleet arms have real fills on this exact refused
cohort (see below) — this report does not distinguish which lane produced which fill.

### Full-population refused cohort

- **60 raw `SKIP_BULL_1100_1200` fires** (account=safe, armed=true) in `core-decisions.jsonl`
  since the ledger's first row (2026-06-25); first fire 2026-07-10 (ledger predates the gate's
  2026-06-18 ratification — the IS/OOS evidence in `safe_bull_1100_1200_gate.json` comes from an
  earlier data source, not this ledger).
- Clustered >=15min apart (`EVENT_CLUSTER_GAP_MINUTES`, same convention as the nightly gate-
  expiry instrument) → **11 distinct episodes**, 2026-07-10 .. 2026-09-03 (today's 11:06 wave
  included).
- **Extra-cohort scan** (FACT): searched every safe-account 11:00-12:00 tick with
  `bull_blockers==[]`, a fired trigger, `bull_score>=11`, and `verdict != SKIP_BULL_1100_1200` —
  62 rows found, but every one is tagged `SKIP_ELITE_BULL_LEVEL_RECLAIM`, `SKIP_STRUCTURE_VETO`,
  or `ENTER_BULL` (the 2026-08-28 11:01-11:05 win — its `trigger_bar_et` is 10:55, before the
  window, so `block_bull_1100_1200`'s own bar-time check never engaged). **Conclusion: the 11
  SKIP-tagged episodes ARE the complete refused cohort** — no shadow population hides under a
  different verdict.

### (1) Forward proxy — sound replay (`walk_exit_manager`, the SAME engine
`gate_expiry_check.py::evaluate_gate_pnl` uses for this exact gate id)

| | value |
|---|---|
| n replayable (`status=ok`) | 8 of 11 (2 `no_contract` — 2026-09-02, cache lag on same-day OPRA; 1 `stale_dropped` — 2026-09-03 today) |
| WR | 50.0% |
| total $ | **-$3.90** (net flat) |
| mean $/trade | -$0.49 |
| bootstrap 95% CI (5,000 resamples) | **[-$99.64, +$94.20]** — straddles zero, not distinguishable from noise |
| drop-top1 / drop-top3 | -$207.30 / -$439.50 |
| `costing_verdict` (gate_expiry_check's own formula) | **GREEN** — "refused cohort would have LOST $-0.49/tr, n=8 — still justified on recent data" |

Cross-check via the **sole-blocker P1 proxy** (day's own next real fill, NOT_REPLAYED,
directional only): 9 of 11 episodes have a same-day real fill to read — 4 WIN / 5 LOSS. Same
direction as the sound replay (flat-to-negative, well under any actionable floor).

### (2) Real-fill cross-reference (fills-ledger.jsonl, FACT)

10 of 11 episodes have a matched same-signal fleet fill (buy on a non-safe-2 arm within
-2..+6min of the refused tick, same right). **40 matched clips, all closed, net +$574.00,
WR 35.0%** (per-clip — arms carry different qty/strike/exit-shape, so this is NOT a scaled
replica of what safe-2 itself would have made; see caveats). Per-episode totals (summed across
arms) **disagree in DIRECTION with the sound replay on 2 of 10 episodes** (08-04 11:26 and
08-04 11:51: sim says winner, real fleet fills both lost; 08-21 11:36: sim says -$223.50 loser,
real fleet fills net +$509 winner) — direct evidence that different arms' strike/exit-shape
choices on the SAME signal diverge in outcome, not just magnitude. Per-arm: safe-3 n=11
sum=+$510 (WR 36.4%), bold-2 n=10 sum=+$249 (WR 50.0%), risky-1 n=10 sum=+$144 (WR 40.0%),
risky-3 n=9 sum=**-$329** (WR 11.1%) — risky-3 (the designated probe arm) is the ONLY arm net
negative on this cohort.

Today's 2026-09-03 11:06 episode (safe-2 refused; bold-2/risky-1/safe-3 entered — matches the
task brief exactly) shows real TP1 partials only (+$657 across 3 clips) — **runners were still
open at report time, so this is a partial/approximate read, not a closed trade.**

### Anchor days (2026-08-06, 08-13, 08-27, 08-28)

| day | episodes | sim $ | real fleet $ | interaction |
|---|---|---|---|---|
| 2026-08-06 | 0 | — | — | **no interaction — gate never fired that day** |
| 2026-08-13 | 1 (11:41) | -$93.00 | -$410.00 (4 clips, all losing) | gate **correctly avoided** a real loser |
| 2026-08-27 | 1 (11:51) | +$151.20 | +$470.00 (4 clips, 3 winning) | gate **cost** a real winner |
| 2026-08-28 | 0 | — | — | **no interaction** (the 11:01-11:05 win used a pre-11:00 trigger bar) |

Net across the only 2 interacting anchor days: sim +$58.20, real +$60.00 — both barely positive,
n=2, not remotely decision-grade. **No regression risk from leaving the gate as-is on any of the
4 named days** (2 had zero interaction; the 2 that interacted roughly cancel).

### Verdict vs. the gate's own ratification (IS n=11 WR=9.1% -$89, OOS n=1 -$42)

The full-population live re-fire (n=8 replayable since 2026-07-10) reads **materially less bad**
than the ratification evidence (flat-to-slightly-negative vs. strongly negative), but it is
**GREEN under `costing_verdict`, not RED** — the refused cohort still nets a (statistically
insignificant) loss, drop-top3 confirms no hidden concentration flatters it, and even the
LOOSEST framing (the recent-20-session nightly slice, YELLOW +$18.3/tr n=7) never clears the
n>=10 floor. **The nightly instrument's own current read for this gate (`gate-registry-
status.json`, run 2026-09-03, window 2026-07-29..2026-09-01) is YELLOW — consistent with this
report.** No evidence bar (RED costing-money smoke alarm, OOS-positive, WF>=0.70, n>=floor) is
cleared. **KEEP. Not actionable even absent the freeze.**

---

## Part B — Filter 10 bull buyer pressure (`f10_vol_mult`, default 0.7, no params key)

### Frozen prereg, run for the first time

`analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json` — cells `baseline
0.70 / relax_50 0.50 / relax_35 0.35 / off 0.0`, gates `oos_positive`, `wf_or_disclosed_null`,
`sub_window_stable`, `anchor_no_regression`, `drop_best`, `decision_floor n>=20`. Its own
`population` field asks for a full 391-day real-OPRA rebuild via the fullhist/orchestrator
battery — **out of scope for this <5min scratch runner; this run scores the frozen gates
against the LIVE-ledger sole-[10] cohort only** (since 2026-07-27, the earliest ledger row
carrying `bull_blockers`), disclosed as a narrower population than the prereg's own frozen
population field asks for.

### Cohort

- Raw sole-[10] HOLD rows: safe 526, bold 529 (both accounts — F10 is baked into
  `filters.py`, not a params-toggled gate, so both engines carry it).
- Per-account clustered episodes: safe 63, bold 63.
- **Cross-account deduped distinct episodes (GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT
  convention, safe+bold refuse the identical market moment): 63.**

### Data-provenance caveat (found live, disclosed prominently)

F10's bar (`ctx.bar`) is exactly `trigger_bar_et` (`heartbeat_core.py`'s own
`bar_ctx.timestamp_et`). Re-evaluating `buyer_pressure_bar_v11` on that SAME bar timestamp
against the **cached backtest SPY/volume series** (not the live intraday feed the engine
actually gated on) does **not** byte-reproduce the live verdict: baseline 0.70 — identical to
the live default — "admits" **24 of 63** (38%) episodes that were live sole-[10]-refused, which
is definitionally impossible on matched data. This is a live-feed-vs-cached-vendor volume
mismatch (same class as the standing data-provenance-strata caveat), not a logic bug in this
runner. **Consequence: absolute per-cell admit counts below are approximate; the ADDED-vs-
baseline delta (same recomputed series at every cell, provenance noise common-mode) is the
primary read.**

### Per-cell sound replay (`walk_exit_manager`), FULL admitted set

| cell | mult | admitted (of 63) | n_ok | WR | total $ | drop-top3 |
|---|---|---|---|---|---|---|
| baseline | 0.70 | 24 | 23 | 47.8% | +$1,995.10 | +$303.20 |
| relax_50 | 0.50 | 32 | 30 | 40.0% | +$1,774.20 | +$82.30 |
| relax_35 | 0.35 | 35 | 33 | 42.4% | +$1,840.05 | +$148.15 |
| off | 0.00 | 35 | 33 | 42.4% | +$1,840.05 | +$148.15 |

The baseline-24 figure is itself a finding (independent of relaxing anything): a third of live
F10-sole refusals disagree with a cached-data recheck of the SAME rule, and forward-replaying
just those disputed 24 nets **+$1,995 / WR 47.8%, surviving drop-top3** — a live-feed/cache
volume-reading discrepancy that plausibly costs real money regardless of what `f10_vol_mult` is
set to. **Flagged, not fixed here** (would need the live intraday volume series, out of scope —
no network calls permitted this session).

### The actual relax question — episodes ADDED beyond baseline

| cell | n added | n ok | WR | total $ | bootstrap 95% CI | drop-top3 |
|---|---|---|---|---|---|---|
| relax_50 | 8 | 7 | 14.3% | **-$220.90** | [-$99.00, +$68.19] | -$468.00 |
| relax_35 | 11 | 10 | 30.0% | **-$155.05** | [-$90.47, +$69.88] | -$636.00 |
| off | 11 | 10 | 30.0% | **-$155.05** | [-$90.47, +$69.88] | -$636.00 |

**Every relax cell's own incremental (added) cohort is net negative**, thin (n=7-10, all below
the prereg's n>=20 decision floor), and already negative before any concentration drop (drop-
top3 makes it worse, confirming it isn't a hidden-winner artifact). relax_35 and `off` produce
an **identical** added set — every bar that clears 0.35 in the cached data also clears 0.0
(consistent: `off` only removes the volume test, not the greenness test, and 0.35 already
admits every green bar this window happened to produce above that ratio).

### (1) Sole-blocker P1 proxy (NOT_REPLAYED, directional)

63 episodes: **25 WIN (cost_money) / 36 LOSS (saved_money) / 2 NONE.** Majority reads
`saved_money` — directionally the gate looks justified — but the flagship watch's own floor
test (`n_cost>=10`) is one-sided and **is** cleared (25>=10), which is exactly why the nightly
instrument (`gate-registry-status.json`, `filter-10-bull-sole`, rolling window
2026-08-05..2026-09-01) currently reads **RED** (39 episodes, 14 cost/25 saved — same
majority-saved-but-floor-cleared shape, smaller window). **This report's full-population number
is directionally consistent with the nightly RED smoke alarm** but the sound-replay ratifying
instrument above (which the nightly RED's own reason text says is required before any action)
shows the ADDED cohort losing money, not making it — the sound replay is the disagreement that
matters and it says NO.

### (2) Real fills where another arm took the sole-[10]-refused tick (FACT)

7 of 63 episodes have a matched real fleet fill (fleet arms are not F10-gated — same
`passed_scoring_peak` rescue-lane mechanism as Part A). **16 matched clips, all closed, net
-$597.00, WR 18.8%.** This is the strongest single piece of evidence in Part B: real paper
capital already tested a slice of this exact refused population, structurally, and it lost
badly.

### Anchor days

| day | episodes | note |
|---|---|---|
| 2026-08-06 | 0 | no interaction |
| 2026-08-13 | 4 | mixed; net P1 read -$79 (3 losers, 1 winner) — refusal net-helped |
| 2026-08-27 | 3 | **all 3 read WIN** (P1 proxy +$303/+$184/+$184) — F10 refused three real winners this day; one (12:24, vol_ratio 0.389) would have been admitted at relax_35/off, the other two are blocked by non-green bars (unfixable by any vol_mult) or already baseline-admitted-per-cache |
| 2026-08-28 | 5 | mixed (2 WIN@527 reused, 3 LOSS@-50 reused — proxy reuses the day's single real trade per side, a known limitation) |

08-27 is the one anchor day where F10 visibly cost real winners; even there, only 1 of 3 missed
episodes is fixable by relaxing (the other 2 fail on bar-greenness, which no `f10_vol_mult`
value changes). Not enough (n=1 fixable/day) to move the verdict.

### Verdict against the prereg's frozen gates, verbatim

| gate | relax_50 | relax_35 | off |
|---|---|---|---|
| `decision_floor` n>=20 (added cohort) | **FAIL** (n=7) | **FAIL** (n=10) | **FAIL** (n=10) |
| `oos_positive` | NOT EVALUATED — no IS/OOS split exists at this n; population too thin to split | same | same |
| `wf_or_disclosed_null` | NOT EVALUATED, same reason | same | same |
| `sub_window_stable` | NOT EVALUATED, n too small to split by month | same | same |
| `anchor_no_regression` | mixed (08-13 helped, 08-27 hurt, n=1-4/day) — no clear regression, but not clean pass either | same | same |
| `drop_best` (added cohort, already reported as drop-top3 above) | still negative | still negative | still negative |

**Every cell fails `decision_floor` outright — the prereg's own pre-registered rule is "below
floor = NO verdict, stays unarmed."** Independent of the floor, the added cohort's OWN sign is
negative in every cell, and the real-fill cross-reference (n=16, -$597, WR 18.8%) and the
nightly RED smoke alarm both point the same direction once you separate "gate looks costly by
the naive P1 floor test" from "the money that would actually be added is negative." **Prereg
hypothesis NOT SUPPORTED. KEEP baseline 0.7. Not actionable even absent the freeze** — and the
live-feed-vs-cache volume mismatch found along the way (Part B's biggest surprise) is a
separate, real, unquantified cost that a params.json threshold change would not fix.

---

## Caveats (apply to both parts)

- Every sound-replay $ figure uses the **cached backtest OPRA/SPY series**, not live quotes — no
  network calls were made this session (per the hard constraint). Today's (2026-09-03) episodes
  in both parts could not be sim-replayed for this reason (`no_contract`/`stale_dropped`); real
  fills fill the gap where available.
- Real-fill cross-reference is a **same-signal detector, not a scaled replica**: matched clips
  come from arms with different qty, strike-selection tables, and exit shapes (safe-3 uses
  safe-2's chart-stop-primary lane; risky-3 uses a looser 0.20 chandelier trail; bold-2/risky-1
  have their own). Sign divergence from the sound replay on 2/10 (Part A) episodes is real, not
  a rounding artifact.
- The sole-blocker P1 proxy reuses "the day's own next (or last) real same-side fill" as a
  stand-in for a refused signal's counterfactual — a single real trade can be reused across
  multiple refused episodes the same day (visible in the 08-28 anchor-day table). Directional
  only, `NOT_REPLAYED`, per the instrument's own documented caveat.
- Bootstrap CIs use 5,000 percentile resamples, n as small as 7 — CIs are wide by construction
  and several straddle zero; reported honestly rather than rounded away.
- Part B's data-provenance mismatch (baseline "should be 0, reads 24/63") means the **absolute**
  admitted counts per cell are approximate; only the added-vs-baseline delta (common-mode noise
  cancels) is treated as decision-relevant here.
