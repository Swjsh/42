# J-SETUP-ANGLES-FINAL — the last three setup angles, tested honestly

> J (2026-06-20): *"cover every angle, use my webull data, test extensively, leave no
> plan untested."* This doc closes the final SETUP-angle batch of
> [docs/J-DATA-RESEARCH-MASTER-PLAN.md](J-DATA-RESEARCH-MASTER-PLAN.md):
> **A6 (calendar/event-day)**, **A7 (level-keyed entry)**, **A10 (self-PnL state)**.
>
> These were flagged up front as **lower-probability than the big finds already shipped**
> (gap-and-go ITM-1 strike, VWAP-cont rvol-floor). The mandate was to test them rigorously
> and honestly — **a negative is a valid tested result.** All three come back **DEAD**, but
> each death is *informative* and each is backed by numbers, not hand-waving.

## Method (the anti-overfit guard)

| Step | Source | Role |
|---|---|---|
| **Part A** | His Webull round-trips (`analysis/webull-j-trades/`, 655 closed 2021-23) | **DEFINES** the hypothesis |
| **Part B** | OUR 2025-26 SPY **real OPRA fills** | **VALIDATES** it forward (OOS / WF / all-cuts / DSR / drop-top5) |

A pattern "real on his data" with **no OUR-data OOS lift = DEAD**, not a win. Headline stat is
**WR + size-neutral pct_move** (raw $ is size-confounded and flagged).

- Script: `backtest/autoresearch/j_setup_angles_a6a7a10.py`
- Scorecard: `analysis/recommendations/j-setup-angles-A6A7A10.json`
- Forward harness: the SAME parameterized VWAP-continuation detector + `_full_metrics` /
  `_ship_gate` / `_verdict_for` OP-22 scorecard **reused verbatim from `j_entry_specificity.py`**
  (no rebuilt fills). Fills = `lib.simulator_real` (causal next-bar-open, chart-stop only).
- Causal (L166): every Part-A feature uses at/before-entry info only; A10 streak state is
  strictly look-back.

---

## Verdicts at a glance

| # | Angle | His-data signal | Forward on OUR data | Tag |
|---|---|---|---|---|
| **A6** | Calendar / OPEX / month-end | **Real & large:** OPEX week 37.1% WR / -8.3 pct_move vs 50.5% / +6.4 (−13.4pp WR). Thu/Fri sharp, Wed worst. w1>w4. | exclude-OPEX OOS +$10/t, WF 0.72 — but **fails a frequency-matched random-removal null (66th pctile, p=0.34)**: indistinguishable from just trading fewer trades. | **DEAD** (live filter); kept as a J-behavioral flag |
| **A7** | Level-keyed entry | **Negative:** his winners did NOT cluster near levels — psych near-vs-mid-air @0.05% = −2.6pp WR, −12.5 pct_move; winner/loser distance identical (0.13% vs 0.12%). | Every *discriminating* proximity bucket goes OOS-NEGATIVE; the only +lift buckets are near-no-ops (remove <5% of trades). | **DEAD** |
| **A10** | Self-PnL "hot read" state | After-win looks +11.2 pct_move sharper — **but it's a day-regime confound.** | N/A — behavioral (no live J trade-stream to filter on). | **DEAD** (confound); real signal = loss-streak tilt = already L168 |

**Net: 0 ships, 3 honest negatives that complete the plan.** No calendar/level/state lever
survives the anti-overfit bar. Two of the three deaths required a *second* statistical control
(frequency-null for A6, day-demeaning for A10) to expose an effect that looked real on the
surface — which is exactly what rigorous negative-testing is for.

---

## A6 — CALENDAR / EVENT-DAY  →  **DEAD** (his signal real, fails frequency-null forward)

**His data — a genuine, mechanistically-sensible pattern:**

| Bucket | n | WR | pct_move (size-neutral) |
|---|---|---|---|
| **OPEX week** (week of 3rd Fri) | 132 | **37.1%** | **−8.3** |
| non-OPEX | 523 | 50.5% | +6.4 |
| month-end (last 3 trading days) | — | — | lift **−7.4** vs rest |
| Thu / Fri (his best DoW) | — | — | +10.1 / +8.9 |
| Wed (his worst DoW) | — | — | −7.5 |
| week-of-month w1 / w4 | 224 / 126 | 54.0% / 39.7% | +14.5 / −7.2 |

J's directional intraday edge **collapses during OPEX week and month-end** — plausible
(OPEX-week dealer gamma pinning suppresses the trending moves his continuation read needs).
This is a real property of his trading and a useful self-discipline flag.

**Forward on OUR data (VWAP-continuation book, 2025-26):**

| Variant | n | exp/t | OOS exp | medWF | all-cuts-OOS+ |
|---|---|---|---|---|---|
| baseline (full morning) | 153 | +$38.3 | +$24.1 | 0.55 | ✗ |
| **exclude-OPEX-week** | 112 | +$43.8 | **+$34.2** | **0.72** | ✗ |
| OPEX-week-only | 41 | +$23.4 | −$0.7 | −1.13 | ✗ |
| his-top-2-DoW (Thu+Fri) keep | 62 | +$32.9 | −$11.3 | −0.21 | ✗ |

The exclude-OPEX variant *looks* like a +$10/t OOS lift. **But the acid test kills it:**

> **Frequency-null control** (remove the same 43 signals AT RANDOM, 200 perms): observed
> +$10.1 lift sits at the **66th percentile** of the random-removal null; **p(random ≥
> observed) = 0.34**. Removing 43 *random* trades produces a lift this big a third of the
> time. The "OPEX edge" on our data is **a frequency-reduction artifact, not a calendar
> edge.** (The DoW filter doesn't even survive the raw gate — Thu/Fri keep goes OOS-negative;
> his DoW ranking does not transfer.)

The late-window negative (0.80 cut OOS-negative for *both* baseline and exclude-OPEX) is the
2026-Q2 put-side drawdown that C1/A9 already own — OPEX exclusion doesn't touch it.

**Verdict: DEAD as a live filter.** His OPEX-week / month-end weakness is real and worth
remembering as a *discretionary* caution, but it is not a wireable edge on our engine.

---

## A7 — LEVEL-KEYED ENTRY  →  **DEAD** (levels too dense; he didn't cluster at them)

**The hypothesis:** did his winning entries cluster near structural levels (round-numbers,
PDH/PDL, overnight hi/lo, session-open) — i.e. is "entered at a level" a winning discriminator
vs "mid-air"?

**Two geometry findings that sink it:**

1. **At SPY's price ($400-600) structural levels are too DENSE for "mid-air" to exist.** A $1
   grid = 0.16-0.25%; the nearest structural level (round-$1/$5 + open + premarket hi/lo +
   intraday pre-entry hi/lo) is within ~0.13% of price for **100% of trades** by the 0.15%
   threshold. (The campaign's earlier `near_level` flag labelling *all 655* trades "near" was
   this same artifact — round-$0.50 made everyone <0.04% from a level. This module re-derived a
   granular ladder to get a real contrast, and confirmed the geometry.)

2. **Where a contrast does exist (tight thresholds), it's NEGATIVE on his data.** Psych-only
   near-vs-mid-air @0.05% (open/premarket/intraday levels, no round numbers): **−2.6pp WR,
   −12.5 pct_move** for "near a level." Winner vs loser mean distance-to-level is *identical*
   (0.127% vs 0.122%). His winners did **not** cluster at levels — if anything mid-air
   (momentum, not level-tied) read slightly better.

**Forward on OUR data** — same conclusion:

| Bucket (psych-only) | removed | OOS exp | verdict |
|---|---|---|---|
| near ≤ 0.02% | 38% of trades | **−$35.4** | discriminates, OOS-NEGATIVE |
| near ≤ 0.03% | ~30% | −$19.2 | discriminates, OOS-NEGATIVE |
| near ≤ 0.05% | ~22% | −$3.8 | discriminates, ~flat-negative |
| near ≤ 0.10% | ~5% | +$26.4 | **NO-OP** (removes almost nothing) |

Every bucket that *meaningfully discriminates* (removes ≥10% of trades) goes OOS-negative; the
only "+lift" bucket is a no-op that proves "everything is near a level." There is no
level-proximity entry filter that both discriminates and lifts.

> **Caveat (disclosed):** J's bar cache has no prior-day bars, so PDH/PDL were unavailable in
> Part A (round/open/premarket/intraday only). OUR Part-B forward test **did** include PDH/PDL
> (continuous data) — and they still didn't help. A dedicated *named-level* feed (the watcher
> fleet's level_source) is richer than computable levels, but the geometry argument (density)
> and the his-data negative both point the same way.

**Verdict: DEAD.** "Trade at a level" is not J's edge and does not improve ours.

---

## A10 — SELF-PnL STATE ("hot read")  →  **DEAD** (day-regime confound)

**The hypothesis (beyond revenge, L168):** was there a "hot read" condition — did J trade
*sharper* after a win / on a win-streak / when his rolling P&L was green? This is about WHEN
his read was sharpest, not sizing.

**The surface result looks like a hot hand:**

| Prior state | n | WR | pct_move |
|---|---|---|---|
| after a WIN | 313 | 52.7% | **+9.4** |
| after a LOSS | 341 | 43.4% | −1.8 |
| win-streak 2+ | 165 | 52.1% | +6.7 |
| **loss-streak 2+** | 192 | **38.0%** | **−6.5** |
| first trade of day | 214 | 46.3% | −6.1 |

After-win is +9.3pp WR / +11.2 pct_move sharper than after-loss. Tempting.

**The confound test kills it.** J takes ~3 trades/day; he wins repeatedly on good trending days
and loses repeatedly on chop days — so "after a win" mostly means "it's a good day," not "I'm
hot." De-mean each trade by **its own day's mean pct_move** and re-test:

| | raw pct_move | **day-demeaned** |
|---|---|---|
| after win | +9.4 | **−3.5** |
| after loss | −1.8 | **+3.2** |
| after-win minus after-loss | **+11.2** | **−6.7 (INVERTS)** |

Once the day-regime is removed, the after-win edge **flips negative** (after-win trades are
slightly *below* the day's own average; same within multi-trade days only). The "hot read after
a win" is **entirely a day-clustering artifact**, not a state effect. Pure noise dressed as a
hot hand — exactly the honest negative the task anticipated.

**The one state signal that IS real:** loss-streak-2+ at 38% WR / −6.5 pct_move — the tilt
cluster. But that is **already L168** (the sizing-up / adding-after-loss killer, captured by
Rule 4 + Rule 6 + the post-loss throttle design). On a *read-quality* basis the loss-streak
penalty is mild; the catastrophe L168 documented was sizing, not the read.

**Verdict: DEAD** as a "hot read" hypothesis. Also un-wireable by construction — A10 is a
property of J's live trade *sequence*, and we have no live J trade-stream to gate our engine on.

---

## What this closes

A6/A7/A10 were the last three **untested** SETUP rows. With these three honest negatives, the
SETUP column of the master plan is **fully tested** (A1-A10 all have verdicts). The campaign's
shippable edges remain the ones already found and validated:

- **gap-and-go bear, ITM-1 strike** (B1 SHIP, LIVE)
- **VWAP-continuation + rvol-floor** (C1 WATCH, flip-ready)
- **everyday bearish-rejection book** (LIVE)

No calendar bucket, level proximity, or PnL-state condition adds a fourth. The value of this
batch is **negative knowledge that prevents future curve-fits**: don't gate on day-of-week
(frequency artifact), don't gate on level proximity (geometry + his own negative), don't gate on
"hot streak" (day-regime confound). Each is now a documented dead-end with the number that
killed it.
