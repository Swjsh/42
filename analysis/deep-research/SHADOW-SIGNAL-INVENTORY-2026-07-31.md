# SHADOW-SIGNAL INVENTORY — how much this engine SEES and cannot ACT on

**Date:** 2026-07-31 (Friday, market closed — after-hours build window)
**Pre-registration:** [`SHADOW-SIGNAL-PREREG-2026-07-31.md`](SHADOW-SIGNAL-PREREG-2026-07-31.md) (filed 17:29:26 ET, before any run)
**Machine state:** `automation/state/shadow-signal-audit.json` · **Measurement:** `SHADOW-SIGNAL-EDGE-2026-07-31.json`
**Regenerated nightly by:** `setup/scripts/shadow_signal_audit.py` (task `Gamma_ShadowSignalAudit`)

---

## VERDICT — promote NOTHING. The quarantine was right.

The 10:15 archetype said the engine sees more than it can act on, and that the silence was
costing money. **Half of that is true.** The engine does see more than it can act on. But when
the shadow signals are measured against real OPRA through the real exit manager, taking every
firing as an entry **loses money** — and **one of the three** (`trendline_reclaim`) loses
significantly at the day level. `wick_reclaim`'s loss is a negative point estimate that is
**not** significant once overlapping positions are blocked by day (Correction 1 below), and
`pullback_hold` is underpowered with **no verdict issued**.

> **CORRECTED 2026-07-31 18:57 ET** by the lane's own adversarial verifier. Two disclosure
> defects were found in the first write-up and are landed below: (1) `wick_reclaim`'s
> significance claim was **n-inflated** and is DOWNGRADED; (2) 90% of trades ran a **−20%
> premium fallback**, not the validated structure cell. **Neither changes a verdict** — the
> exit bias runs CONSERVATIVE, so the null strengthens. Every number on this page was
> re-derived this session by re-running `backtest/tools/shadow_signal_edge_2026_07_31.py`;
> the baseline block is byte-identical to the original run.

| signal | unbiased n | days | total P&L | per-trade | WR | drop-best | **day-level test** | verdict |
|---|---|---|---|---|---|---|---|---|
| `trendline_reclaim` | 27 | 3 | **−$1,097** | −$40.64 | 14.8% | −$1,121 | **stat −3.401, p=0.00067, 3/3 days negative** | **SIGNIFICANT NEGATIVE — stands unqualified**, keep quarantined |
| `wick_reclaim` | 133 | 3 | **−$2,556** | −$19.22 | 16.5% | −$3,075 | **stat −0.649, p=0.516, 2/3 days negative** | **Negative point estimate, NOT significant at day level** ⬅ downgraded — keep quarantined |
| `pullback_hold` | 0 | 0 | — | — | — | — | — | **UNDERPOWERED — NO VERDICT ISSUED (untested, not dead)** |

For both measured signals, `drop_best` makes the total **worse**, not better: there is no single
lucky trade propping these up. They are consistently unprofitable as standalone entry triggers.

### ⬅ CORRECTION 1 — `wick_reclaim` is NOT statistically significant (downgraded)

The first write-up called it "BH-SIG NEGATIVE" off a **per-trade** p of 0.059. That test treats
133 firings as 133 independent draws, and they are not: on 2026-07-20 alone **52 trades ran
across only 8 distinct contracts**, and the detector fires on **57% of RTH 5-min bars**, so
positions overlap near-continuously. The pre-registration promised day-level block aggregation;
day sums were printed but **no day-level test was ever computed.**

It is computed now (`day_level_test()`, in the harness, so a re-run reproduces it):

| signal | day sums | statistic | p | days negative | reading |
|---|---|---|---|---|---|
| `wick_reclaim` | −2,520 / **+1,737** / −1,773 | −0.649 | **0.516** | 2/3 | one strongly positive day; the mean is not distinguishable from zero |
| `trendline_reclaim` | −397 / −166 / −534 | −3.401 | **0.00067** | 3/3 | every block negative — **this one stands** |

The per-trade BH result is retained in the JSON as `bh_fdr_q010_significant_PER_TRADE` for
provenance, but it is **no longer the verdict field.** Method disclosed: statistic = mean/SE over
day-sums, two-sided p by normal approximation (`one_sample_p`) — the same estimator the per-trade
screen uses, on n=3 blocks. Both signals stay quarantined either way; the *claim* is what changed,
not the decision.

> ⚠️ **ESTIMATOR SENSITIVITY — read before quoting `trendline_reclaim`'s p to anyone.** The p
> above is a **normal approximation**, which is optimistic at n=3 blocks. Under a proper Student-t
> with df=2 the same statistics give **`trendline_reclaim` p=0.077** (not 0.00067) and
> **`wick_reclaim` p=0.583** (not 0.516). `trendline_reclaim` keeps its **significant-negative**
> label here — it is the verdict of record, and its qualitative case is strong independent of the
> estimator (3/3 day-blocks negative, −$40.64/trade, worse at the true −50% cap). But **the
> headline "p=0.0007" is an artifact of the normal approximation, not a robust n=3 result** — do
> not carry that number into a promotion argument without more days. **No decision changes:** both
> signals stay quarantined, nothing is armed, and `pullback_hold` still has no verdict. What is
> disclosed here is the *strength* of the claim, not its direction.

### ⬅ CORRECTION 2 — the validated exit cell never reached 90% of these trades

The harness intended to walk exits under the **validated structure cell** (structure stop primary,
−50% catastrophe cap). `ExitState.from_entry` resolves structure mode only when the shape declares
it **AND** `structure_stop_enabled` **AND** a `trigger_level` is present. `trigger_level` is absent
on most shadow firings, so those trades silently fell back to **premium mode at −20%** — which
`RIBBON_RIDE`'s own source note calls the flag-OFF emergency fallback, **not** the validated cell.
Textbook C14 / L248 dead-knob-by-omission, inside a harness whose docstring promised otherwise.

Re-derived this session (now emitted as `exit_fallback_correction` in the JSON):

| fact | value |
|---|---|
| resolved trades on unbiased days | 160 |
| **missing `trigger_level`** | **144 = 90.0%** |
| exit stages | premium_stop **87**, ribbon_flip_back 37, structure_stop **16**, time_stop 12, runner_stop 8 |
| realized premium-stop range | **−20.9% … −19.0%** — every one at the −20% fallback, **none near −50%** |
| structure_stop legs | **16 — exactly the 16 trades that carried a `trigger_level`** |

**Direction of bias: CONSERVATIVE. The reported figures FLATTER these signals.** Re-walked with
the stop set to the true −50% catastrophe cap:

| signal | as reported (−20% fallback) | at the true −50% cap |
|---|---|---|
| `wick_reclaim` | −$2,556 | **−$6,462** |
| `trendline_reclaim` | −$1,097 | **−$1,588** |

Negative in both configurations. **The NULL verdict survives and strengthens** — which is exactly
why this is a disclosure correction, not a re-opened question. Reproduce:
`python backtest/tools/shadow_signal_edge_2026_07_31.py` → `counterfactual_true_cap`.

### ⬅ SCOPE — what was tested, and what must NOT be graveyarded

Only the **STANDALONE-TRIGGER** form was measured: "take every firing as an entry." Their use as
**score contributors, tiebreakers, or vetoes is UNTESTED** and must not be swept into the
graveyard — gate interactions are multiplicative (C15), and a signal that is useless alone can
still be additive in a cascade. `pullback_hold` likewise: **n=0 resolvable, NO verdict issued.
It is untested, not dead.**

`pullback_hold` began firing 2026-07-23; **no day after 07-22 has unbiased OPRA coverage**, so it
has n=0 measurable events. Per the pre-registration it gets a coverage number and no verdict.

### The finding that matters most: being right at 10:15 does not make the signal right

`wick_reclaim` fired at 10:21 on 2026-07-31 into a +4.82 bounce and was architecturally mute.
That single firing was correct. The **population** of its firings loses $19.22 per trade. This is
lesson **C24** verbatim — *anchor trades are one-off exceptional setups; the general population of
the same pattern class may be losers* — and it is the exact trap a forensic finding invites you
to walk into. The 10:15 case proves the wiring gap is **real**; it does not prove the signal is
**good**. Those are two different claims and only the first survived measurement.

### Why they lose: they are ambient, not selective

| signal | firings per RTH 5-min bar | reading |
|---|---|---|
| `wick_reclaim` | **0.572** | fires on 57% of all bars — this is a weather report, not a trigger |
| `pullback_hold` | 0.362 | 36% of bars |
| `trendline_reclaim` | 0.162 | 16% of bars — the only one with trigger-like selectivity, and it loses worst per trade |

Cluster **C27** sets the bar at "detectors firing >80% of *days* measure noise". `wick_reclaim`
fires on 57% of *bars*, which is far past that line. The payoff ratio is healthy (mean win
+$144.74 vs mean loss −$55.35, 2.6:1) — the hit rate (16.3%) is what kills it. Nothing is wrong
with the detector's geometry; it simply is not a scarce event, and 0DTE theta punishes
non-scarcity.

**This vindicates the 2026-07-15 decision to log these and keep them off the score.** That
quarantine was not over-caution — it kept a **significantly-negative** trigger
(`trendline_reclaim`) and a **negative-but-underdetermined** one (`wick_reclaim`) out of live
scoring, and it held the line on a third nobody has been able to measure yet. The eval-first gate
did its job. (Precision matters here: only ONE of the three is statistically significant — see
Correction 1. The quarantine is still right; the *reason* is one signal proven bad and two not
proven good, which is a weaker and more honest claim than the original write-up made.)

---

## The measurement, and the artifact it nearly produced

**This result flipped sign under an artifact hunt, so the hunt is reported first.**

The naive all-days run said `wick_reclaim` was **+$603** and `pullback_hold` **+$1,665**. Both
were artifacts of **OPRA cache selection**. The cache was populated by prior studies, so which
`(date, strike)` pairs exist is not random:

| date | SPY range | ATM strikes needed | cached | unbiased? |
|---|---|---|---|---|
| 2026-07-20 | 742.00–748.54 | 8 | 15 | **YES** |
| 2026-07-21 | 744.89–748.97 | 5 | 13 | **YES** |
| 2026-07-22 | 747.31–749.98 | 4 | 12 | **YES** |
| 2026-07-23 | 736.37–741.85 | 7 | 0 | no |
| 2026-07-27 | 736.45–744.66 | 10 | 0 | no |
| 2026-07-28 | 737.23–742.59 | 7 | 2 | no |
| 2026-07-29 | 731.90–742.62 | 12 | 3 | no |
| 2026-07-30 | 736.64–739.08 | 3 | 0 | no |
| 2026-07-31 | 738.61–748.47 | 10 | 4 | no |

On 2026-07-31 only strikes 744/745/746/748 are cached while SPY ranged 738.61–748.47. **Only
events from the upper third of the day can resolve** — precisely where a bullish signal wins. That
one day contributed +$4,534 to `wick_reclaim` and +$3,370 to `pullback_hold`. Restricting to days
whose cached ladder spans the whole SPY range moves `wick_reclaim` from **+$603 to −$2,556**.

A day is admitted only if its cached strike ladder covers every ATM strike the day's SPY range
implies, computed from the cache and the observed range — never hand-listed.

### Method (locked in the pre-registration, not chosen after seeing results)

- **Event unit** = `(signal, date, 5-min bar)`. The detector reads the last *closed* 5-min bar, so
  consecutive 1-min ticks inside one bar are the same detection. Counting ticks would have
  inflated n ~4× (2,118 tick-firings → 362 real events for `wick_reclaim`) and faked significance.
- **Entry** = entry+1 ([`ENTRY-BAR-CONVENTION-RULING-2026-07-25`](../../markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md));
  `walk_exit_manager`'s strict `>` means the entry bar is never exit-checked.
- **Strike** = ATM, read from `crypto/lib/strike_selection.py#V15_SAFE_TIERS` (core Safe under
  $10K), verified against the live table rather than assumed — the BS-sim-ignored-`strike_offset`
  scar cost a weekend of research.
- **Exit** = the **real** `exit_manager.plan_exit_actions` core via `lib.exit_manager_walk`, driven
  with the `RIBBON_RIDE` `ExitShape` heartbeat_core actually registers — not `simulate_trade_real`,
  which is known-divergent. ⚠️ **AS INTENDED, NOT AS RUN:** the shape declares structure-stop
  primary with a −50% catastrophe cap, but **144/160 trades (90%) had no `trigger_level`** and
  therefore ran the **−20% premium fallback** instead. See Correction 2 — bias is CONSERVATIVE
  and the verdicts are unchanged, but this bullet described an exit cell most trades never got.
- **Size** = qty 3 (Rule 6 minimum: 2 TP + 1 runner). All dollars are minimum-size.
- **Real OPRA only.** Nothing Black-Scholes-synthesized; uncovered cells are excluded and counted.
- **Multiplicity** — BH-FDR q≤0.10 across all three signals on the *unbiased* slice (testing the
  biased one would be significance-shopping on a known artifact). ⚠️ **The per-trade BH result is
  no longer the verdict** — it is n-inflated by overlapping positions; the **day-level block test**
  adjudicates (Correction 1).

**Harness sanity (checked before believing the negative):** exit stages are diverse
(premium_stop 87, ribbon_flip_back 37, structure_stop 16, time_stop 12, runner_stop 8 of 160), the
worst loss is −43.5% of position cost, and wins reach +$518.63 — the walk is not clipping upside or
short-circuiting into a single stop path. **The stage mix is also the evidence for Correction 2:**
all 16 `structure_stop` legs come from the 16 trades that carried a `trigger_level`, and all 87
`premium_stop` legs fired between −20.9% and −19.0% — the −20% fallback, never the −50% cap.

### What this does NOT prove

These signals were tested as **standalone entry triggers that take every firing**. This does not
show they carry zero information as a *score contributor*, a *tiebreaker*, or a *veto*. A signal
that is unprofitable alone can still be additive in a cascade. That is a different, larger
experiment (and gate interactions are multiplicative — cluster C15). What is now measured and
closed: **no shadow signal should be promoted to a standalone trigger.**

It also does **not** prove `wick_reclaim` is a losing signal *at all*: its day-level test is
p=0.516 on 3 blocks. The honest statement is "not shown to be good," not "shown to be bad."
And it says **nothing** about `pullback_hold`, which has zero resolvable events.

---

## The architecture finding: SHADOW ≠ ORPHANED, and only one is a bug

The sweep separates three things that look identical from the outside:

- **SHADOW_BY_DESIGN** — logged-only on purpose, with a *dated decision* and, where it sits on the
  live path, an *existing named guard test* pinning the quarantine. This is discipline, not debt.
- **RESEARCH_ONLY** — consumed by backtest/eval tooling, never claimed live. Fine.
- **ORPHANED** — nothing reads it and no decision says it should be shadow. Dead weight.

**Result: 1 true orphan in the registered set.** `detect_candlestick_pattern_bullish`
(`backtest/lib/filters.py:334`) has **zero references in the entire tree, including tests**. Its
bearish twin `detect_candlestick_pattern_bearish` is wired into `evaluate_bearish_setup`. A bull
mirror was written and never connected to anything — the same asymmetry the 2026-07-15
directional-gate research found and partially fixed.

The shadow surfaces are, by contrast, **correctly quarantined and correctly documented**. The rig
is not accidentally blind here; it made a deliberate choice and — per the measurement above —
the right one.

### Two false claims this audit caught (including one of its own)

L249 says never accept a docstring's word for it. Two claims failed a direct grep:

1. **`analysis/trendlines/trendline-log.jsonl` has ZERO programmatic readers.** The natural
   assumption — that `trendline_outcomes.py` / `trendline_break_replay.py` consume it — is
   **false**; those read `break-outcomes.jsonl` and `break-dataset.jsonl`, different files. The
   trendline log is read by humans and ad-hoc analysis only.
2. **This audit's own registry asserted a shadow quarantine for `pullback_hold` and
   `trendline_reclaim` without naming the guard test that proves it.** The checker flagged both as
   `UNPROVEN_SHADOW` on its first run — against its author. `test_pullback_hold_shadow_only.py`
   and `test_bull_trendline_wick_reclaim_shadow_only.py` do exist; the registry was corrected to
   cite them. A shadow claim with no dated decision is now mechanically downgraded to ORPHANED.

### Known limits of the checker

Grep sees **call structure**, not **data flow**. It cannot see that a detector's result was
assigned to a logged-only field. For anything sitting on a live-path file, the substitute is a
*named, existing guard test* — which is why `SHADOW_BY_DESIGN` demands one and reports
`UNPROVEN_SHADOW` when it is missing. Freshness monitors (`engine_health.py`) and a state file's
own producer are excluded from consumer counts, so a dead file cannot look alive because a health
check watches its mtime.

---

## Ranked promotion queue — ARM NOTHING

| rank | candidate | status | why |
|---|---|---|---|
| — | `wick_reclaim` → trigger | **REJECTED** | −$19.22/trade over 133 firings, 57% of bars (ambient, not a trigger), −$6,462 at the true −50% cap. **Not significant at day level (p=0.516)** — rejected as "not shown to be good", not "proven bad" |
| — | `trendline_reclaim` → trigger | **REJECTED** | −$40.64/trade, **day-level p=0.00067, 3/3 days negative**, −$1,588 at the true −50% cap |
| 1 | `pullback_hold` → trigger | **BLOCKED — no data, NO VERDICT** | n=0 unbiased; needs OPRA for 07-23+. Untested, **not** graveyarded |
| 2 | `trendlines-live.json` → engine consumer | **not evaluated** | RTH-only + shadow; another agent owns the multi-day lane |
| 3 | shadow signals as *score contributors* (not triggers) | **open question** | the standalone test does not settle it; C15 says gates interact multiplicatively |

**Cleanup shipped:** none of the above. The one actionable item is the orphan
`detect_candlestick_pattern_bullish` — flagged, **not deleted this fire**. It is dead code with no
consumer, so deleting it is safe, but it is also the natural building block for a bull candlestick
trigger if the directional-gate work wants one. It is now on a standing surface instead of being
invisible; the delete-or-wire call belongs with the directional-gate lane, not this one.

**What would unblock rank 1:** the in-flight OPRA backfill. `pullback_hold` becomes measurable the
moment 2026-07-23 onward has a full ATM ladder. Re-run
`backtest/tools/shadow_signal_edge_2026_07_31.py` — it recomputes the unbiased-day set from the
cache automatically, so it will simply widen when the data lands.

---

## 🔧 REVERT PROCEDURE — commit `bc1263e4` (READ BEFORE REVERTING)

**`git revert bc1263e4` ALONE IS NOT ENOUGH AND LEAVES A SILENT FAILURE.** The commit shipped a
Windows scheduled task that is NOT tracked in git. Reverting deletes
`setup/scripts/shadow_signal_audit.py` while `Gamma_ShadowSignalAudit` stays registered against a
now-missing absolute path, firing nightly into nothing. It fails OPEN (a dead task cannot block
trading or J's session), but it is exactly the C7 silent-failure shape this lane was built to
detect — so it is written down instead of remembered.

**Both steps, in this order:**

```powershell
# 1. Unregister the nightly task FIRST (before the script disappears)
Unregister-ScheduledTask -TaskName Gamma_ShadowSignalAudit -Confirm:$false

# 2. Then revert the commit
git revert bc1263e4        # from C:\Users\jackw\Desktop\42, after-hours only

# 3. Verify nothing is left pointing at a deleted script
Get-ScheduledTask -TaskName Gamma_ShadowSignalAudit -ErrorAction SilentlyContinue   # -> nothing
```

**Leftovers that are safe to keep or delete by hand** (untracked, no consumer once the script is
gone): `automation/state/shadow-signal-audit.json`,
`automation/state/logs/shadow-signal-audit.std{out,err}.log`. The
`## Known broken` line in `automation/overnight/STATUS.md` is a human log entry — prune it by hand
per OP-22, do not expect the revert to touch it.

**Current task state, verified 2026-07-31 19:03 ET (`Get-ScheduledTask` / `Get-ScheduledTaskInfo`):**

| field | value |
|---|---|
| TaskName / TaskPath | `Gamma_ShadowSignalAudit` / `\` |
| State | **Ready** |
| LastRunTime | 2026-07-31 17:02:50 MT = **19:02:50 ET** (post-TZ-fix re-fire) |
| LastTaskResult | **0** |
| NextRunTime | 2026-08-01 15:25 MT = **17:25 ET** |
| Action | `wscript.exe //nologo run_exe_hidden.vbs backtest\.venv\Scripts\pythonw.exe setup\scripts\shadow_signal_audit.py` |

Re-registering after a revert-of-the-revert: `setup/install-shadow-signal-audit.ps1` (shipped in
the same commit) is idempotent and re-creates the task.

---

## 🐛 FIXED 2026-07-31 evening — the instrument's own TZ bug

`shadow_signal_audit.py` stamped every artifact with `dt.datetime.now()` — **bare Mountain local
time rendered with an " ET" suffix.** This box is on Mountain time (ET = local + 2h), so the
machine state, this doc's AUTOGEN header, and the STATUS.md line it wrote were all **2h early and
mislabeled** — the repo's most-scarred defect class, committed by the instrument that exists to
catch exactly this kind of silent wrongness.

- **Fix:** a single `stamp_et()` helper backed by `setup/scripts/et_clock.py` (DST-aware).
- **Guard:** `backtest/tests/test_shadow_signal_audit_2026_07_31.py::test_generated_stamp_is_real_ET`
  asserts the emitted `generated_at_et` is within 60s of `et_clock`, plus two companions covering
  `stamp_et()` itself and both rendered surfaces.
- **RED-PROOF:** reverting `stamp_et()` to `dt.datetime.now()` fails the guard with
  `AssertionError: generated_at_et=2026-07-31T16:50:05 is 7201s from et_clock ET (2026-07-31T18:50:05)`.
- **Same bug, same commit:** `backtest/tools/shadow_signal_edge_2026_07_31.py:338` had an identical
  `dt.datetime.now()` stamp on the measurement JSON — fixed in the same pass.
- All stamps on this page and in `automation/state/shadow-signal-audit.json` have been **restamped**
  by re-running the corrected instrument through the real scheduled task (empty stderr).

---

## 🔄 REFRESHED 2026-08-09 — `trendline_reclaim` re-tested on 9 more OPRA days, verdict HOLDS (and an artifact caught along the way)

Task: decide whether `detect_trendline_reclaim_bullish` (the bull mirror of the LIVE
`trendline_rejection` bear trigger) graduates out of shadow. Per the standing "recency >
aggregate" doctrine (J 2026-07-31), this was NOT a re-citation of the numbers above — the OPRA
cache grew since this page was written (08-01..08-07 are now cached; they were not on 07-31), so
the standalone-trigger test was re-run on the WIDER window using the SAME machinery
(`backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py`, imports
`shadow_signal_edge_2026_07_31.py`'s `fully_covered_days`/`run_one`/`day_level_test`/`EXIT_SHAPE`
verbatim, does not re-derive them).

**Raw "take every firing as an entry" (this page's own original method) on the wider 10-unbiased-
day set LOOKED positive: +$7,120.85, n=142.** That is an artifact, caught before being reported as
a finding (fable-too-good discipline): 2026-07-29 alone contributed **+$10,107.47** from **15
firings on consecutive 5-min bars during one uninterrupted trend**, each independently scored as
its own trade by a methodology that (as this page's own §"SCOPE" already disclosed) "takes every
firing as an entry" with no single-position constraint — the real system is single-position-per-
account (Rule 4, C11). A position-limited re-walk of the SAME events (a firing only counts as
tradeable if the account would actually be flat — i.e. the prior kept trade's own exit has already
happened) kept only **75 of 152** raw firings as real opportunities and the total flips back
negative: **-$1,110.16, -$14.80/trade, 8/10 days negative, day-majority FAILS (2/10), drop-best
FAILS (-$1,879.07 remaining)**. The original verdict — **REJECTED, keep quarantined** — stands,
now on more than 3x the day-count and under a methodology hardened against the exact overlap
artifact the original 3-day sample never happened to expose.

**Tuesday 2026-08-04 (the live book's best real day, +$3,624 across all 5 accounts) is
untouched by any version of this**: `trendline_reclaim` fired **zero times in shadow** that date,
confirmed across core (safe+bold) and all 3 fleet decision ledgers.

Full writeup + the position-limited-rewalk methodology: `analysis/deep-research/
TRENDLINE-BULL-AND-CHART-2026-08-09.md`. Raw artifact: `analysis/deep-research/
BULL-TRENDLINE-RECLAIM-GRADUATION-2026-08-09.json`. Ranked promotion queue entry for
`trendline_reclaim` below is unchanged (still REJECTED) — this section adds evidence, it does not
reopen the decision.

---

<!-- BEGIN AUTOGEN: shadow_signal_audit.py -- do not hand-edit below -->

_Regenerated by `setup/scripts/shadow_signal_audit.py` at 2026-08-08T17:25:51 ET._

**15 registered producers | 1 ORPHANED | 0 DRIFT vs registry | 29 unregistered producer-shaped defs**

| id | kind | classification | live | rsrch | test | detects | output reaches | evidence |
|---|---|---|---|---|---|---|---|---|
| `candlestick_pattern_bullish` | detector | **ORPHANED** | 0 | 0 | 1 | bullish candlestick pattern (hammer / bullish engulfing / bullish marubozu) | NOWHERE -- zero references in the entire tree incl. tests | zero non-test callsites anywhere in the tree |
| `context_bundle` | state_file | **SHADOW_BY_DESIGN** | 1 | 1 | 2 | multi-timeframe trend alignment (daily/hourly/m15) + events + prior-day context | heartbeat_core rec dict -> core-decisions.jsonl (LOGGED ONLY) (age 1.06d) | quarantine pinned by an existing named guard test |
| `pullback_hold` | detector | **SHADOW_BY_DESIGN** | 1 | 1 | 2 | pullback into a level zone that holds N bars | shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `trendline_log` | state_file | **SHADOW_BY_DESIGN** | 0 | 1 | 0 | every detected trendline instance, per fire | NOTHING reads it in code -- producer + a recovery utility + docs only (age 1.06d) | dated decision on record; 1 research consumer(s), 0 live |
| `trendline_reclaim` | detector | **SHADOW_BY_DESIGN** | 1 | 0 | 2 | close reclaiming a fitted descending trendline | shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `trendlines_live` | state_file | **SHADOW_BY_DESIGN** | 0 | 2 | 0 | respected multi-day SPY trendlines (wick + body families, RTH-only) | confluence_producer.py + engine_health freshness only -- NO decision consumer (age 1.06d) | dated decision on record; 2 research consumer(s), 0 live |
| `wick_reclaim` | detector | **SHADOW_BY_DESIGN** | 1 | 3 | 4 | bullish wick rejection reclaiming a tracked level | BullishSetupResult.shadow_triggers_fired -> engine_cli base dict -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `confluence_zones` | state_file | **RESEARCH_ONLY** | 0 | 1 | 1 | scored confluence zones (>=2 sources within +/-0.85) | NOTHING outside its own producer -- confirmed zero consumers TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14 and re-confirmed 2026-07-31 (age 1.06d) | 1 callsite(s), none on the live decision path |
| `fvg` | detector | **RESEARCH_ONLY** | 0 | 1 | 1 | fair value gap | erl_irl_watcher (backtest/eval only, not on the live path) | 1 callsite(s), none on the live decision path |
| `candlestick_pattern_bearish` | detector | **WIRED** | 1 | 0 | 1 | bearish candlestick pattern | evaluate_bearish_setup -> bear_score | 1 live-path callsite(s) |
| `confluence` | detector | **WIRED** | 1 | 1 | 2 | multiple levels stacked near price | triggers_fired | 1 live-path callsite(s) |
| `level_reclaim` | detector | **WIRED** | 1 | 14 | 6 | closed bar reclaiming a tracked level | triggers_fired -> bull_score/routing | 1 live-path callsite(s) |
| `level_rejection` | detector | **WIRED** | 1 | 12 | 6 | rejection at a tracked level | triggers_fired -> bear_score/routing | 1 live-path callsite(s) |
| `ribbon_flip_bullish` | detector | **WIRED** | 1 | 2 | 0 | EMA ribbon restack to BULL | ribbon_just_flipped_bullish -> scoring | 1 live-path callsite(s) |
| `sequence_reclaim` | detector | **WIRED** | 1 | 0 | 2 | break-then-reclaim sequence on a level | evaluate_bullish_setup | 1 live-path callsite(s) |

### Unregistered producer-shaped defs (candidate new orphans)

| module | symbol | line |
|---|---|---|
| `backtest/lib/filters.py` | `detect_sequence_rejection` | 458 |
| `backtest/lib/filters.py` | `detect_wick_rejection_bearish` | 544 |
| `backtest/lib/filters.py` | `detect_trendline_rejection_bearish` | 601 |
| `backtest/lib/filters.py` | `detect_ribbon_flip_bearish` | 716 |
| `backtest/lib/filters.py` | `evaluate_bullish_setup` | 1089 |
| `backtest/lib/filters.py` | `evaluate_bearish_setup` | 1378 |
| `backtest/lib/filters.py` | `detect_vwap_reclaim_failed_break` | 1832 |
| `backtest/lib/filters.py` | `detect_vix_regime_dayside` | 1927 |
| `backtest/lib/filters.py` | `detect_lbfs` | 2026 |
| `backtest/autoresearch/trendline_engine.py` | `find_pivots` | 202 |
| `crypto/lib/chart_patterns.py` | `scan_all_contra_regime` | 1114 |
| `crypto/lib/chart_patterns.py` | `scan_high_edge_contra_regime` | 1150 |
| `crypto/lib/chart_patterns.py` | `scan_high_edge_near_named` | 1185 |
| `crypto/lib/market_structure.py` | `classify_trend` | 100 |
| `crypto/lib/market_structure.py` | `detect_structure_break` | 168 |
| `crypto/lib/market_structure.py` | `analyze_structure` | 213 |
| `crypto/lib/confluence.py` | `compute_confluence` | 172 |
| `backtest/lib/structure_shift.py` | `detect_structure_shift_bear` | 64 |
| `backtest/lib/structure_shift.py` | `detect_structure_shift_bull` | 126 |
| `backtest/lib/level_strength.py` | `score_level` | 228 |
| `backtest/lib/level_strength.py` | `find_confluences` | 331 |
| `backtest/lib/level_strength.py` | `compute_vwap` | 387 |
| `backtest/lib/level_strength.py` | `compute_volume_profile` | 433 |
| `setup/scripts/context_bundle_producer.py` | `compute_trend_alignment` | 204 |
| `setup/scripts/context_bundle_producer.py` | `compute_events_context` | 369 |
| `setup/scripts/context_bundle_producer.py` | `compute_prior_day` | 426 |
| `setup/scripts/context_bundle_producer.py` | `compute_rvol_session_so_far` | 446 |
| `setup/scripts/context_bundle_producer.py` | `compute_today_context` | 485 |
| `setup/scripts/context_bundle_producer.py` | `compute_levels_context` | 541 |

<!-- END AUTOGEN -->
