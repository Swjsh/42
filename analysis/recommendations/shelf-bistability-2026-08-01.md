# Shelf bistability SOURCE-FIX A/B — Next-Twelve #7 (verifier-endorsed follow-up to WS3)

**Verdict: NULL — hysteresis-only (`114a7a6b`) STANDS.** All three source-fix arms (ARM_A,
ARM_B, ARM_AB) kill flicker at the merge and improve the proxy entry population's real-OPRA
P&L — but **all three unanimously fail the pre-registered steady-state-fidelity gate**: a
mechanism that stops the greedy merge from flip-flopping intraday also, in doing so, resolves
roughly half of all trading days' contested regions toward a *different, permanently-shifted*
winner than today's forming-bar-included baseline. `daily_context.py` and
`refresh_levels_intraday.py` are **untouched** by this study. Prereg `07697c7d` (committed
BEFORE the runner existed) → runner `backtest/tools/shelf_bistability_source_fix_2026_08_01.py`
→ this result.

---

## 1. Mechanism (named, reproduced, validated)

`daily_context._find_shelf_candidates` seeds a $1.60-wide candidate band at every unique
close/high/low across ~40 trailing daily bars **plus today's own still-forming bar**, and
scores every bar — today's included — as a touch. `_merge_shelf_candidates` then does a
greedy strongest-first, ties-to-lower-`band_low`, non-overlap merge. Because today's forming
H/L/C keep changing every 5-min refresh, which historical candidate today's own bar happens to
touch keeps changing too — and in a region with two-or-more near-tied overlapping candidates,
that's enough to flip the merge's winner, renaming the written level.

**Concrete flip, quoted exactly (2026-07-31, real production fire timestamps):**

| Fire | Forming bar (so far) | `[741.56,743.16]` (742.36) | `[742.45,744.05]` (743.25) | `[740.80,742.40]` (741.60) | Region winner |
|---|---|--:|--:|--:|---|
| 09:43:37 | O 745.06 H 746.55 **L 742.79 C 743.12** | 10 touches | 9 touches (today counted) | 9 touches | **742.36 alone** |
| 09:48:37 | O 745.06 H 746.55 **L 741.98 C 742.28** | 10 touches | 8 touches (today NO LONGER counted) | 10 touches (today now counted) | **{741.60, 743.25}** — 742.36 is GONE |

One ordinary 5-minute bar (-$0.81 low, -$0.84 close, no level broken) re-tiles the merge across
the whole $740.50–744.05 region — a genuine 5-way exact tie at 10 touches appears at 09:48
(`740.80-742.40`, `741.56-743.16`, `741.69-743.29`, `741.75-743.35`, and a **transient candidate
seeded by today's own new close**, `742.28-743.88` — direct, mechanical proof of forming-bar
self-seeding). Validated at full 5-min cadence across the whole 2026-07-31 RTH session against
the REAL observed A/B state sequence in the WS3 guard fixture (`core-decisions.jsonl`-sourced):
**63/77 fires match exactly (81.8%)**, consistent with WS3's own disclosed ~85% reproduction
fidelity on a differently-scoped check. Full method + the sparser 6-day real-snapshot
cross-check (4/11 exact, all mismatches at premarket/first-16-minute boundary noise): prereg §1.

## 2. Method (391-day population, real data only)

- **Population:** RTH sessions 2025-01-02..2026-07-31, the VERIFIED 391-day population
  (identical construction to WS5/WS6/WS11: 3 half-days excluded, 2026-06-15 gap day in).
  Asserted before any cell ran.
- **Refresh cadence (simulated):** `:MM:37` ET, `MM%5==3`, 09:33–15:53 — identical to the real
  `Gamma_LevelRefresh` fire schedule and WS3's own guard fixture. 77 fires/day.
- **Daily bars:** REAL SIP daily bars fetched fresh this session via the same Alpaca endpoint
  `daily_context._fetch_daily_bars` uses (459 bars, 2024-10-01..2026-07-31 — not resampled;
  some early test days' 60-cal-day lookback reaches before the 5m cache begins).
- **SPY 5m / OPRA:** the established `load_extended_data` lineage (`spy_5m_2025-01-01_2026-07-22.csv`
  + post-07-22 tail of `spy_5m_2026-05-19_2026-07-31.csv`) and real cached OPRA contract bars
  (14,399 files), et-v2 frame throughout (DST-correct, C6).
- **Four arms**, all sharing the unmodified `_find_shelf_candidates` primitive:
  - **BASELINE** = current HEAD, unmodified.
  - **ARM_A** = incumbent-stable literal tie-break (candidates included today's forming bar,
    same as BASELINE; on an EXACT touch-count tie, the candidate matching — by mid, within
    the same `$0.10` epsilon hysteresis itself uses — the immediately-prior refresh's kept
    band wins). Incumbent threaded continuously across the full 391-day×77-fire timeline.
  - **ARM_B** = exclude the forming bar from candidate-finding entirely (bars with `date < D`
    only) — the SAME pattern already used elsewhere in this file (`_prior_day_hlc`) and in
    `shelf_hold_reclaim_study.py`. Structurally flicker-proof by construction (candidate input
    literally does not change intraday) — proven, not assumed, by guard.
  - **ARM_AB** = ARM_A's tie-break fed ARM_B's candidates.
- **Metrics:** (a) flicker — RAW (pre-hysteresis) and WRITTEN (post the REAL, unmodified
  `_hysteresis_carry`, N=5) transition counts, full population + recent-25; (b) steady-state
  fidelity — EOD (15:53, post-hysteresis) shelf-mid set vs BASELINE's, per day (gating), plus a
  non-gating full-day-union diagnostic; (c) downstream entry impact — `detect_level_reclaim`
  (F1 time gate only, disclosed scope) against each arm's active written anchors, real OPRA
  fills, `walk_exit_manager` against the byte-asserted CONTROL registry exit shape, on a
  **proof-pruned** day set (334-345/391 days per arm where sequences provably diverge from
  BASELINE — verified by assertion, not sampled; the remaining days are proven byte-identical
  across all four arms, so their P&L contribution is exactly zero by construction).
- **A bug the guard suite caught before any number was trusted:** the first draft of ARM_A's
  incumbent match used band-*overlap*, which spuriously flagged multiple mutually-overlapping
  contested candidates as "incumbent" simultaneously and silently defeated the tie-break.
  `test_arm_a_resolves_the_named_tie_toward_incumbent` failed RED, was fixed to mid-within-
  `$0.10` identity matching, and the **full population was re-run** — every number below is
  post-fix.

## 3. Results — all four arms, full population

| Metric | BASELINE | ARM_A | ARM_B | ARM_AB |
|---|--:|--:|--:|--:|
| Written flips, full pop | 5,494 | 4,098 (−25.4%) | 965 (−82.4%) | 929 (−83.1%) |
| Written flips, recent-25 | 514 | 302 (−41.2%) | 51 (−90.1%) | 46 (−91.1%) |
| Days with any written flip | 333/391 | 327/391 | 233/391 | 229/391 |
| **EOD fidelity divergence days (GATING)** | — | **250/391 (63.9%)** | **198/391 (50.6%)** | **276/391 (70.6%)** |
| Full-day union divergence days (diagnostic) | — | 289 | 248 | 299 |
| Median divergence magnitude ($) | — | 0.58 | 0.53 | 0.52 |
| Entry-population n (proof-pruned days) | 643 | 613 | 531 | 530 |
| Entry-population total P&L | −$10,855.05 | −$9,417.15 | −$6,665.10 | −$6,413.45 |
| **P&L delta vs BASELINE, full pop** | — | **+$1,437.90** | **+$4,189.95** | **+$4,441.60** |
| Entries: gained / lost / moved | — | 123 / 153 / 60 | 137 / 249 / 54 | 178 / 291 / 69 |
| Recent-25 P&L delta vs BASELINE | — | **+$1,367.85** | **+$635.45** | **+$715.85** |

**Gates (frozen in prereg §5):**

| Gate | ARM_A | ARM_B | ARM_AB |
|---|:--:|:--:|:--:|
| G1 flicker materially reduced | PASS | PASS | PASS |
| **G2 steady-state fidelity preserved** | **FAIL** | **FAIL** | **FAIL** |
| G3 entry P&L not degraded (full + recent-25) | PASS | PASS | PASS |
| **Ships?** | **NO** | **NO** | **NO** |

## 4. Why this is a real, decisive null — not a rounding call

G2 is the unanimous blocker, and it fails by a wide margin, not a borderline one: 198–276 of
391 days (51–71%) show at least one shelf whose end-of-session identity permanently differs
from BASELINE's, at a **median** magnitude of ~$0.52–0.58 (a real, tradeable-level-sized
difference, not a cent of float noise). The mechanism is intuitive in hindsight: **by 15:53 ET
today's own forming bar is, for all practical purposes, real, completed price action** — it is
not "incomplete data" anymore, it is the day's actual structure. BASELINE legitimately lets
that data act as a tie-breaking touch; every arm tested here either discards it entirely
(ARM_B/AB) or adds a *different* kind of memory (incumbent stickiness, ARM_A) that resolves the
SAME kind of near-tied region toward a different local optimum than BASELINE's memoryless
daily recompute. **Any mechanism that adds stability to this greedy top-1 merge trades
intraday flicker for baseline-relative identity drift — none of the three tested designs
escapes that trade-off.** This is a stronger, more general finding than "ARM_B specifically
doesn't work" — it says the *class* of fixes tried here has a structural ceiling.

One disclosed measurement nuance: the reported **max** divergence magnitude touches $14+ on a
handful of days (e.g. 2025-10-17), but inspection shows this is a nearest-pair-heuristic
artifact — an arm-only price with no real BASELINE counterpart in its own region gets
force-paired against an unrelated distant BASELINE-only price when the two sets have different
cardinality that day. The **median** ($0.52–0.58) is the honest summary statistic; the
per-day divergence *counts* (which drive the gate) do not depend on this pairing heuristic at
all — only the magnitude characterization does. Disclosed, not hidden.

**Prereg prediction checked, one deviation found:** ARM_AB was predicted to be numerically
identical to ARM_B (§3, "checked, not assumed"). Confirmed exactly on 390/391 days; on
2025-03-04 the two diverge slightly because ARM_AB carries incumbent memory **across day
boundaries** (a real property of ARM_A's mechanism) while ARM_B is memoryless by construction
— a rare (1/391), fully explained, non-bug deviation, disclosed here and in the guard suite.

## 5. Disposition

Per the pre-committed outcome (prereg §7): **no arm clears its gates → hysteresis-only stands.
No production file is touched.** `setup/scripts/daily_context.py` and
`refresh_levels_intraday.py` are byte-identical to `114a7a6b` after this study; guards pin
their unmodified merge-function source so a future silent drift is caught. This closes the
Next-Twelve #7 question with evidence: the symptom-level fix (hysteresis) is not just
"good enough for now" — on this evidence it is currently *better calibrated* than any of the
three natural source-level alternatives tried, because it damps flicker without altering which
level the engine ultimately converges on.

**A future idea, explicitly NOT executed this session** (would need its own pre-registration):
a fix that only starts trusting today's forming bar once the session is materially complete
(e.g. after some fraction of RTH has printed) might capture BASELINE's late-session fidelity
while still damping the worst of the mid-day wobble — but any such threshold is exactly the
kind of hand-picked knob this codebase's own doctrine (never hand-picked; pre-registered A/B
only) requires evidence for, not intuition. Not proposed as a recommendation, just named as the
next falsifiable question if anyone revisits this.

## 6. Artifacts

- Prereg: `analysis/recommendations/shelf-bistability-prereg-2026-08-01.md` (`07697c7d`)
- Runner: `backtest/tools/shelf_bistability_source_fix_2026_08_01.py`
- Full cell data: `analysis/recommendations/shelf-bistability-2026-08-01.json`
- Guards (6, incl. RED-proof): `backtest/tests/test_shelf_bistability_2026_08_01.py`
- Runtime: 63.5s, $0 (pure Python + cached/real REST data, no LLM).
