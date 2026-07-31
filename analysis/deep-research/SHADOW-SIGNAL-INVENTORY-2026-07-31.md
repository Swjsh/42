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
firing as an entry **loses money** — and two of the three lose significantly under BH-FDR.

| signal | unbiased n | days | total P&L | per-trade | WR | drop-best | p | BH q≤0.10 | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `trendline_reclaim` | 27 | 3 | **−$1,097** | −$40.64 | 14.8% | −$1,121 | 1.9e−08 | **SIG** | NEGATIVE — keep quarantined |
| `wick_reclaim` | 133 | 3 | **−$2,556** | −$19.22 | 16.5% | −$3,075 | 0.059 | **SIG** | NEGATIVE — keep quarantined |
| `pullback_hold` | 0 | 0 | — | — | — | — | — | — | **UNDERPOWERED — no verdict** |

For both measured signals, `drop_best` makes the total **worse**, not better: there is no single
lucky trade propping these up. They are consistently unprofitable as standalone entry triggers.

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
quarantine was not over-caution — it prevented two significantly-negative triggers from reaching
live scoring. The eval-first gate did its job.

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
  with the `RIBBON_RIDE` `ExitShape` heartbeat_core actually registers (structure stop primary,
  −50% catastrophe cap, TP1 +100% sell 66.7%, trailing runner 15% off HWM) — not `simulate_trade_real`,
  which is known-divergent.
- **Size** = qty 3 (Rule 6 minimum: 2 TP + 1 runner). All dollars are minimum-size.
- **Real OPRA only.** Nothing Black-Scholes-synthesized; uncovered cells are excluded and counted.
- **BH-FDR q≤0.10** across all three signals, run on the *unbiased* slice — testing the biased one
  would be significance-shopping on a known artifact.

**Harness sanity (checked before believing the negative):** exit stages are diverse
(premium_stop 54%, ribbon_flip_back 23%, structure_stop 10%, time_stop 8%, runner_stop 5%), the
worst loss is −43.5% of position cost (inside the configured −50% cap), and wins reach +$518.63 —
the walk is not clipping upside or short-circuiting into a single stop path.

### What this does NOT prove

These signals were tested as **standalone entry triggers that take every firing**. This does not
show they carry zero information as a *score contributor*, a *tiebreaker*, or a *veto*. A signal
that is unprofitable alone can still be additive in a cascade. That is a different, larger
experiment (and gate interactions are multiplicative — cluster C15). What is now measured and
closed: **no shadow signal should be promoted to a standalone trigger.**

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
| — | `wick_reclaim` → trigger | **REJECTED** | −$19.22/trade, BH-significant negative, 57% of bars |
| — | `trendline_reclaim` → trigger | **REJECTED** | −$40.64/trade, p=1.9e−08 negative |
| 1 | `pullback_hold` → trigger | **BLOCKED — no data** | n=0 unbiased; needs OPRA for 07-23+ |
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

<!-- BEGIN AUTOGEN: shadow_signal_audit.py -- do not hand-edit below -->

_Regenerated by `setup/scripts/shadow_signal_audit.py` at 2026-07-31T16:10:10 ET._

**15 registered producers | 1 ORPHANED | 0 DRIFT vs registry | 29 unregistered producer-shaped defs**

| id | kind | classification | live | rsrch | test | detects | output reaches | evidence |
|---|---|---|---|---|---|---|---|---|
| `candlestick_pattern_bullish` | detector | **ORPHANED** | 0 | 0 | 1 | bullish candlestick pattern (hammer / bullish engulfing / bullish marubozu) | NOWHERE -- zero references in the entire tree incl. tests | zero non-test callsites anywhere in the tree |
| `context_bundle` | state_file | **SHADOW_BY_DESIGN** | 1 | 1 | 2 | multi-timeframe trend alignment (daily/hourly/m15) + events + prior-day context | heartbeat_core rec dict -> core-decisions.jsonl (LOGGED ONLY) (age 0.09d) | quarantine pinned by an existing named guard test |
| `pullback_hold` | detector | **SHADOW_BY_DESIGN** | 1 | 0 | 2 | pullback into a level zone that holds N bars | shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `trendline_log` | state_file | **SHADOW_BY_DESIGN** | 0 | 0 | 0 | every detected trendline instance, per fire | NOTHING reads it in code -- producer + a recovery utility + docs only (age 0.09d) | ZERO programmatic readers -- ad-hoc/human research only, but a dated decision keeps it on purpose |
| `trendline_reclaim` | detector | **SHADOW_BY_DESIGN** | 1 | 0 | 2 | close reclaiming a fitted descending trendline | shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `trendlines_live` | state_file | **SHADOW_BY_DESIGN** | 0 | 1 | 0 | respected multi-day SPY trendlines (wick + body families, RTH-only) | confluence_producer.py + engine_health freshness only -- NO decision consumer (age 0.09d) | dated decision on record; 1 research consumer(s), 0 live |
| `wick_reclaim` | detector | **SHADOW_BY_DESIGN** | 1 | 2 | 4 | bullish wick rejection reclaiming a tracked level | BullishSetupResult.shadow_triggers_fired -> engine_cli base dict -> core-decisions.jsonl (LOGGED ONLY) | quarantine pinned by an existing named guard test |
| `confluence_zones` | state_file | **RESEARCH_ONLY** | 0 | 1 | 1 | scored confluence zones (>=2 sources within +/-0.85) | NOTHING outside its own producer -- confirmed zero consumers TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14 and re-confirmed 2026-07-31 (age 0.09d) | 1 callsite(s), none on the live decision path |
| `fvg` | detector | **RESEARCH_ONLY** | 0 | 1 | 1 | fair value gap | erl_irl_watcher (backtest/eval only, not on the live path) | 1 callsite(s), none on the live decision path |
| `candlestick_pattern_bearish` | detector | **WIRED** | 1 | 0 | 0 | bearish candlestick pattern | evaluate_bearish_setup -> bear_score | 1 live-path callsite(s) |
| `confluence` | detector | **WIRED** | 1 | 1 | 1 | multiple levels stacked near price | triggers_fired | 1 live-path callsite(s) |
| `level_reclaim` | detector | **WIRED** | 1 | 12 | 6 | closed bar reclaiming a tracked level | triggers_fired -> bull_score/routing | 1 live-path callsite(s) |
| `level_rejection` | detector | **WIRED** | 1 | 12 | 5 | rejection at a tracked level | triggers_fired -> bear_score/routing | 1 live-path callsite(s) |
| `ribbon_flip_bullish` | detector | **WIRED** | 1 | 2 | 0 | EMA ribbon restack to BULL | ribbon_just_flipped_bullish -> scoring | 1 live-path callsite(s) |
| `sequence_reclaim` | detector | **WIRED** | 1 | 0 | 2 | break-then-reclaim sequence on a level | evaluate_bullish_setup | 1 live-path callsite(s) |

### Unregistered producer-shaped defs (candidate new orphans)

| module | symbol | line |
|---|---|---|
| `backtest/lib/filters.py` | `detect_sequence_rejection` | 478 |
| `backtest/lib/filters.py` | `detect_wick_rejection_bearish` | 564 |
| `backtest/lib/filters.py` | `detect_trendline_rejection_bearish` | 621 |
| `backtest/lib/filters.py` | `detect_ribbon_flip_bearish` | 736 |
| `backtest/lib/filters.py` | `evaluate_bullish_setup` | 1109 |
| `backtest/lib/filters.py` | `evaluate_bearish_setup` | 1370 |
| `backtest/lib/filters.py` | `detect_vwap_reclaim_failed_break` | 1794 |
| `backtest/lib/filters.py` | `detect_vix_regime_dayside` | 1889 |
| `backtest/lib/filters.py` | `detect_lbfs` | 1988 |
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
