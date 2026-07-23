# STRATEGY PORTFOLIO SYNTHESIS — 2026-07-23

> J's directive: "good traders make money most days; we need a few solid strats." This doc joins
> tonight's 6-lane kitchen cook (`analysis/kitchen/`) to the engine's own 18.5-month full-history
> replay (`analysis/recommendations/engine-fullhist-replay-2026-07-23.md`) and asks one question:
> **does anything researched tonight move the live engine off "trades 36% of days, loses on the
> median day it does trade" and toward "wins most days"?** Survivors input for this synthesis: `[]`.
> Verdict up front: **no.** Full reasoning, numbers, and the honest path forward below.
>
> Sources: `analysis/kitchen/HARVEST-DAY-ANATOMY-2026-07-23.md`, `analysis/kitchen/day-archetype-map.json`,
> all 6 cook lanes' episodes/results/prereg JSON, `analysis/recommendations/engine-fullhist-replay-2026-07-23.{md,json}`,
> `markdown/doctrine/FOCUS-DOCTRINE.md`. Analysis-only — no live wiring, no params.json edits, no
> commits to trading-path files, no orders. BH-FDR across all 83 cells computed fresh for this doc
> (methodology in §1); every other number is read verbatim from the cited source, not re-derived
> except where explicitly marked ESTIMATE.

---

## 0. Headline

| | |
|---|---|
| **Current live engine (RIDE_THE_RIBBON only, 18.5mo)** | 36.4% of days traded, $+13.09/calendar-day avg, **median $/trading-day = -$63.00** |
| **Tonight's 6 cook lanes, 83 total cells** | **0 cells** clear both (a) the lane's own 4-gate ship bar AND (b) portfolio-wide BH-FDR at q≤0.10 |
| **Ship candidates from tonight** | **NONE** (matches the `survivors: []` input to this task) |
| **Closest miss** | `class-conditional-exits` cell A6 (tighten TRENDLINE-tier stops) — only 4/4-gate cell all night, best day-win-rate of any candidate (67.4%), but fails the 83-cell portfolio correction (q=0.31, not q=0.066 as its own 13-cell lane reported) |
| **Cleanest kills** | `range-day-fade` (16/16 dead, confirms a 2nd independent range-entry-family failure) and `trend-day-continuation` (16/16 dead — the trend archetype's level-touch bottleneck survives a non-level attack) |

---

## 1. THE FULL COOK TABLE — all 83 cells, portfolio-wide BH-FDR

**Methodology (computed by this doc, not inherited from any lane):** each lane pre-registered and
reported its own within-lane Benjamini-Hochberg FDR (q(BH-13), q(BH-16), q(BH-12) etc.) — correct
for that lane's own multiple-comparison problem, but tonight ran **6 independent lanes = 83 total
hypothesis tests against the same underlying 190-trade/386-day population family**. A cell that
looks significant inside its own 13-cell grid can be pure noise once corrected against the full
night's search surface. Standard BH procedure applied once across all 83 `p_raw` values pooled
(sorted ascending, `q_i = min(q_{i+1}, p_i · 83/rank_i)`), q≤0.10 per the project's own standing
convention (matches every individual lane's own q₀.10 bar). Full computation:
`C:\Users\jackw\AppData\Local\Temp\claude\...\scratchpad\bh_fdr.py` (ad hoc, not committed —
re-run trivially from the 6 source JSONs cited per lane below if this needs auditing).

**Result: 3 of 83 cells survive q≤0.10 — zero of them are ship-eligible entry/exit candidates:**

| cell | lane | p_raw | q(BH-83) | why it doesn't ship |
|---|---|--:|--:|---|
| `trendline_compressed_lt75c_STACKED_AM_0935_1159` | trendline-family-refinement | 0.00000 | 0.0000 | **It's a proven LOSER** (-$705.60, 0/4 gates, n=8) — significant because it's reliably bad, not good. Read as an exclusion-filter candidate, not an entry. |
| `B1_PRIORCHOP-TIGHT` | class-conditional-exits | 0.00001 | 0.0004 | 2/4 gates — day_wr 17.4% and held-out -$40.58 both fail. A p=0.00001 driven by a handful of huge trades, not day-consistency (see §3 caveat). |
| `C1_DIAG-CHOP-TIGHT` | class-conditional-exits | 0.00048 | 0.0133 | Explicitly `NOT_GATE_ELIGIBLE_NONCAUSAL_DIAGNOSTIC` by the lane's own pre-reg design — diagnostic only, structurally excluded from gating regardless of q. |

**The night's only 4/4-gate cell (A6, class-conditional-exits) does NOT survive:** q(BH-83)=0.3076
vs. its own-lane q(BH-13)=0.066. This is the single most important number in this synthesis — it's
the difference between "ship" and "keep watching" for the night's best candidate, and it only
shows up once you correct across the full search surface instead of each lane grading its own homework.

### A. class-conditional-exits (13 cells)

Tightens TRENDLINE-tier's pre-TP1 premium stop (T) and/or the post-TP1 chandelier trail (TR) off
the current -20%/15% control. Source: `analysis/kitchen/class-conditional-exits-episodes.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) | note |
|---|--:|--:|:--:|--:|--:|---|
| A1_T-CTRL_TR-CTRL | 0 | +$0.00 | 0/4 | 1.00000 | 1.0000 | CONTROL_HOLDS |
| A2_T-TIGHT_TR-CTRL | 73 | +$1,423.02 | 3/4 | 0.04392 | 0.3076 | CONTROL_HOLDS |
| A3_T-LOOSE_TR-CTRL | 67 | -$640.60 | 1/4 | 0.71712 | 1.0000 | CONTROL_HOLDS |
| A4_T-CTRL_TR-TIGHT | 23 | +$306.60 | 3/4 | 0.00737 | 0.1529 | CONTROL_HOLDS |
| A5_T-CTRL_TR-WIDE | 23 | -$176.30 | 0/4 | 0.67087 | 0.9769 | CONTROL_HOLDS |
| **A6_T-TIGHT_TR-TIGHT** | **95** | **+$1,718.72** | **4/4** | 0.02029 | **0.3076** | lane-local "SHIP", portfolio KILL |
| A7_T-TIGHT_TR-WIDE | 95 | +$1,268.52 | 3/4 | 0.08527 | 0.3076 | CONTROL_HOLDS |
| A8_T-LOOSE_TR-TIGHT | 90 | -$343.30 | 1/4 | 0.62088 | 0.9202 | CONTROL_HOLDS |
| A9_T-LOOSE_TR-WIDE | 90 | -$891.25 | 0/4 | 0.78421 | 1.0000 | CONTROL_HOLDS |
| B1_PRIORCHOP-TIGHT | 24 | +$737.64 | 2/4 | 0.00001 | 0.0004 | CONTROL_HOLDS |
| B2_PRIOROTHER-WIDE | 20 | -$60.90 | 0/4 | 0.56178 | 0.8967 | CONTROL_HOLDS |
| C1_DIAG-CHOP-TIGHT | 17 | +$420.56 | 3/4 | 0.00048 | 0.0133 | NOT_GATE_ELIGIBLE_NONCAUSAL_DIAGNOSTIC |
| C2_DIAG-NONCHOP-WIDE | 21 | -$96.10 | 0/4 | 0.59626 | 0.9106 | NOT_GATE_ELIGIBLE_NONCAUSAL_DIAGNOSTIC |

### B. day-archetype-gate (16 cells)

Causal opening-range-compression classifier (30/60-min window, k=0.60/0.75 threshold, skip-day or
half-size, VIX confirmation on/off) — skips or de-sizes days it flags as chop-like before entry.
Source: `analysis/kitchen/day-archetype-gate-episodes.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) |
|---|--:|--:|:--:|--:|--:|
| N30_k060_skip_vixOFF | 170 | +$1,138.00 | 3/4 | 0.07899 | 0.3076 |
| N30_k060_skip_vixON | 172 | +$1,022.20 | 3/4 | 0.08493 | 0.3076 |
| N30_k060_half_vixOFF | 190 | +$569.00 | 3/4 | 0.11174 | 0.3076 |
| N30_k060_half_vixON | 190 | +$511.10 | 3/4 | 0.11559 | 0.3076 |
| **N30_k075_skip_vixOFF** | 145 | **+$2,434.30** | 3/4 | 0.02751 | 0.3076 | best pnl-lift cell all night |
| N30_k075_skip_vixON | 148 | +$2,236.90 | 3/4 | 0.03207 | 0.3076 |
| N30_k075_half_vixOFF | 190 | +$1,217.15 | 3/4 | 0.06868 | 0.3076 |
| N30_k075_half_vixON | 190 | +$1,118.45 | 3/4 | 0.07335 | 0.3076 |
| N60_k060_skip_vixOFF | 169 | +$1,084.70 | 3/4 | 0.07964 | 0.3076 |
| N60_k060_skip_vixON | 171 | +$958.70 | 3/4 | 0.08622 | 0.3076 |
| N60_k060_half_vixOFF | 190 | +$542.35 | 3/4 | 0.11170 | 0.3076 |
| N60_k060_half_vixON | 190 | +$479.35 | 3/4 | 0.11593 | 0.3076 |
| N60_k075_skip_vixOFF | 153 | +$1,503.05 | 3/4 | 0.05500 | 0.3076 |
| N60_k075_skip_vixON | 157 | +$1,201.85 | 3/4 | 0.06764 | 0.3076 |
| N60_k075_half_vixOFF | 190 | +$751.52 | 3/4 | 0.09301 | 0.3076 |
| N60_k075_half_vixON | 190 | +$600.93 | 3/4 | 0.10218 | 0.3076 |

**Every single cell clears 3/4 gates and every cell's pnl-lift is positive** — this is a real,
construct-valid classifier (its own pre-reg discloses 62-79% of gated days genuinely carry the
day-inventory's own `chop` label). It still KILLS on gate 2 (`day_majority`) in all 16 cells,
because skip-day cells move day win rate the WRONG direction (-1.4pts vs baseline 34.04%) — the
classifier zeroes some genuinely-winning trend/range days alongside its intended chop losers,
trading fewer, richer, LESS consistent days. Per FOCUS-DOCTRINE §3 (day-consistency ranks above
total $), this is a **correct KILL, not a close call** — full self-audit already in the lane's own
pre-reg (`analysis/kitchen/prereg-day-archetype-gate-2026-07-23.json`).

### C. extra-lanes-fullhist (10 cells)

First-ever full-history batch replay for 4 of the 6 "extra" detectors that place real Safe-paper
orders **live today** (`bollinger_squeeze`, `vwap_reclaim_failed_break`, `gap_and_go` [WATCH-only],
`double_bottom_base_quiet`) — a measurement-hole-closing study, not a new-signal search.
`vwap_continuation` and `vix_regime_dayside` (2 of the 6 live extra setups) still have **no
full-history harness at all** — disclosed gap, not evaluated here. Source:
`analysis/kitchen/extra-lanes-fullhist-results-2026-07-23.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) |
|---|--:|--:|:--:|--:|--:|
| bollinger_squeeze\|sq_recent=2 | 196 | +$984.41 | 3/4 | 0.38612 | 0.6819 |
| bollinger_squeeze\|sq_recent=4\|**BASELINE (live)** | 237 | +$2,014.68 | 3/4 | 0.11115 | 0.3076 |
| bollinger_squeeze\|sq_recent=6 | 257 | +$2,157.24 | 3/4 | 0.11581 | 0.3076 |
| vwap_reclaim_failed_break\|entry_cutoff=10:00 | 24 | +$681.63 | 3/4 | 0.29402 | 0.6039 |
| vwap_reclaim_failed_break\|entry_cutoff=10:30\|**BASELINE (live)** | 59 | +$1,712.27 | 2/4 | 0.05937 | 0.3076 |
| vwap_reclaim_failed_break\|entry_cutoff=11:00 | 72 | +$1,986.63 | 2/4 | 0.03430 | 0.3076 |
| gap_and_go\|side=put\|BASELINE (WATCH-only) | 15 | -$1,502.65 | 0/4 | 0.10207 | 0.3076 |
| gap_and_go\|side=both | 55 | -$3,030.71 | 0/4 | 0.02916 | 0.3076 |
| double_bottom_base_quiet\|not_near_named=False\|**BASELINE (live)** | 115 | **-$2,564.07** | 1/4 | 0.14464 | 0.3531 |
| double_bottom_base_quiet\|not_near_named=True | 21 | +$8.95 | 2/4 | 0.98858 | 1.0000 |

**Audit flag, not a cook finding:** `double_bottom_base_quiet` is armed and placing real Safe-paper
orders live today; its full-history baseline is net **-$2,564.07** in tuning and **-$940.25** in
held-out ($-3,504.32 combined) at only 1/4 gates. `gap_and_go` (both cells net-negative, 0/4 gates)
confirms its WATCH-only status is correct. This is a re-audit flag for the orchestrator, not a
proposal to disable anything from this doc.

### D. range-day-fade (16 cells)

Fades the CURRENT day's own compressed opening range back toward the interior, gated on a causal
range-archetype classifier (distinct from range-pingpong's multi-day S/R levels). Source:
`analysis/kitchen/range-day-fade-results.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) |
|---|--:|--:|:--:|--:|--:|
| rdf-w30-t035-b015-c0 | 456 | -$8,937.28 | 0/4 | 0.99890 | 1.0000 |
| rdf-w30-t035-b015-c1 | 324 | -$6,062.37 | 1/4 | 0.99130 | 1.0000 |
| rdf-w30-t035-b030-c0 | 486 | -$8,819.58 | 0/4 | 0.99760 | 1.0000 |
| rdf-w30-t035-b030-c1 | 342 | -$6,418.52 | 1/4 | 0.98960 | 1.0000 |
| rdf-w30-t050-b015-c0 | 705 | -$10,991.93 | 0/4 | 0.99710 | 1.0000 |
| rdf-w30-t050-b015-c1 | 486 | -$5,518.22 | 0/4 | 0.92131 | 1.0000 |
| rdf-w30-t050-b030-c0 | 767 | -$10,582.16 | 0/4 | 0.99260 | 1.0000 |
| rdf-w30-t050-b030-c1 | 529 | -$5,990.20 | 0/4 | 0.92941 | 1.0000 |
| rdf-w60-t035-b015-c0 | 332 | -$6,861.67 | 0/4 | 0.99900 | 1.0000 |
| rdf-w60-t035-b015-c1 | 227 | -$3,079.98 | 1/4 | 0.92381 | 1.0000 |
| rdf-w60-t035-b030-c0 | 403 | -$7,893.39 | 0/4 | 0.99980 | 1.0000 |
| rdf-w60-t035-b030-c1 | 279 | -$5,324.13 | 0/4 | 0.99140 | 1.0000 |
| rdf-w60-t050-b015-c0 | 583 | -$12,836.41 | 0/4 | 1.00000 | 1.0000 |
| rdf-w60-t050-b015-c1 | 393 | -$6,678.76 | 1/4 | 0.99520 | 1.0000 |
| rdf-w60-t050-b030-c0 | 695 | -$14,101.88 | 0/4 | 1.00000 | 1.0000 |
| rdf-w60-t050-b030-c1 | 480 | -$9,695.30 | 0/4 | 0.99980 | 1.0000 |

**16/16 negative, every q=1.0.** Unambiguous kill, no honest-null nuance needed.

### E. trend-day-continuation (16 cells)

Non-level continuation vocabulary for trend days (opening-range-breakout-hold, ribbon-persist
pullback-to-VWAP) — deliberately NOT a level-touch trigger, testing whether the trend archetype's
best-traded-economics/worst-coverage gap can be closed without RIDE_THE_RIBBON's level requirement.
Source: `analysis/kitchen/trend-day-continuation-results-2026-07-23.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) |
|---|--:|--:|:--:|--:|--:|
| or_breakout_hold\|depth0.20\|window11:30\|confirm_none | 206 | -$4,520.30 | 0/4 | 0.14234 | 0.3531 |
| or_breakout_hold\|depth0.20\|window11:30\|confirm_resume | 181 | -$2,311.01 | 0/4 | 0.51208 | 0.8334 |
| or_breakout_hold\|depth0.20\|window14:00\|confirm_none | 220 | -$4,452.98 | 0/4 | 0.15913 | 0.3669 |
| or_breakout_hold\|depth0.20\|window14:00\|confirm_resume | 203 | -$2,872.64 | 0/4 | 0.43745 | 0.7410 |
| or_breakout_hold\|depth0.40\|window11:30\|confirm_none | 226 | -$3,302.81 | 0/4 | 0.34830 | 0.6424 |
| or_breakout_hold\|depth0.40\|window11:30\|confirm_resume | 200 | -$3,763.32 | 0/4 | 0.32014 | 0.6039 |
| or_breakout_hold\|depth0.40\|window14:00\|confirm_none | 237 | -$3,863.55 | 0/4 | 0.27785 | 0.6039 |
| or_breakout_hold\|depth0.40\|window14:00\|confirm_resume | 219 | -$4,179.49 | 0/4 | 0.28504 | 0.6039 |
| ribbon_trend_persist\|depth0.20\|window11:30\|confirm_none | 198 | -$1,704.45 | 1/4 | 0.60343 | 0.9106 |
| ribbon_trend_persist\|depth0.20\|window11:30\|confirm_resume | 173 | -$4,746.39 | 1/4 | 0.11859 | 0.3076 |
| ribbon_trend_persist\|depth0.20\|window14:00\|confirm_none | 229 | -$3,626.49 | 1/4 | 0.31094 | 0.6039 |
| ribbon_trend_persist\|depth0.20\|window14:00\|confirm_resume | 212 | -$6,860.83 | 1/4 | 0.03817 | 0.3076 |
| ribbon_trend_persist\|depth0.40\|window11:30\|confirm_none | 219 | -$49.34 | 1/4 | 0.98862 | 1.0000 |
| ribbon_trend_persist\|depth0.40\|window11:30\|confirm_resume | 188 | -$3,030.30 | 1/4 | 0.36959 | 0.6669 |
| ribbon_trend_persist\|depth0.40\|window14:00\|confirm_none | 238 | -$945.34 | 1/4 | 0.79864 | 1.0000 |
| ribbon_trend_persist\|depth0.40\|window14:00\|confirm_resume | 222 | -$5,191.15 | 1/4 | 0.15117 | 0.3585 |

**16/16 negative total_pnl, 0 cells clear more than 1/4 gates.** Non-level trend vocabulary does
NOT close the trend-archetype gap — see §3 for what this implies about the actual bottleneck.

### F. trendline-family-refinement (12 cells)

Conditions the existing (live) TRENDLINE-tier admission bar on ribbon spread/stack state and
entry-hour window — a narrowing-only study on a proven live-fills winner class, per its own
pre-reg. Source: `analysis/kitchen/trendline-family-refinement-episodes.json`.

| cell_id | n | tuning $ | gates | p_raw | q(BH-83) |
|---|--:|--:|:--:|--:|--:|
| trendline_compressed_lt75c_MIXED_MIDDAY_1200_1259 | 1 | +$545.65 | 2/4 | 1.00000 | 1.0000 |
| trendline_compressed_lt75c_MIXED_AM_0935_1159 | 4 | +$384.60 | 1/4 | 0.50198 | 0.8333 |
| trendline_compressed_lt75c_MIXED_PM_1300_1500 | 10 | +$570.05 | 1/4 | 0.42351 | 0.7323 |
| trendline_wide_ge75c_STACKED_PM_1300_1500 | 19 | -$386.00 | 1/4 | 0.57759 | 0.9045 |
| trendline_wide_ge75c_STACKED_MIDDAY_1200_1259 | 14 | -$504.60 | 1/4 | 0.31909 | 0.6039 |
| trendline_compressed_lt75c_STACKED_MIDDAY_1200_1259 | 7 | -$291.90 | 1/4 | 0.31946 | 0.6039 |
| trendline_wide_ge75c_STACKED_AM_0935_1159 | 15 | -$683.90 | 1/4 | 0.18226 | 0.4088 |
| trendline_wide_ge75c_MIXED_AM_0935_1159 | 0 | +$0.00 | 0/4 | 1.00000 | 1.0000 |
| trendline_wide_ge75c_MIXED_MIDDAY_1200_1259 | 0 | +$0.00 | 0/4 | 1.00000 | 1.0000 |
| trendline_wide_ge75c_MIXED_PM_1300_1500 | 0 | +$0.00 | 0/4 | 1.00000 | 1.0000 |
| trendline_compressed_lt75c_STACKED_PM_1300_1500 | 17 | -$826.85 | 0/4 | 0.06808 | 0.3076 |
| **trendline_compressed_lt75c_STACKED_AM_0935_1159** | 8 | **-$705.60** | 0/4 | 0.00000 | **0.0000** | portfolio-significant LOSER |

**Population is too thin to ship anything** (95 tuning trades / 12 cells ≈ 7.9/cell; the only
n≥15 cells are all STACKED and all lose). The one portfolio-significant result (p=0.0) is a
reliably-bad combination (STACKED ribbon + AM window), useful as an exclusion signal, not an entry.
MIXED-ribbon-state trades (19 total in the whole 124-trade population) trend directionally
positive but every MIXED cell is below the n≥15 evidence floor — genuinely too little data to
call, not a hidden win being suppressed.

---

## 2. THE PORTFOLIO VIEW — day-archetype × strategy coverage

### 2.1 Coverage grid

| Archetype (n days / 386) | Traded-day economics | Live RIDE_THE_RIBBON | Live extra-setups (full-hist where measured) | Tonight's 6 candidates |
|---|---|---|---|---|
| **trend** (97 total, 59 sit-out = 60.8%) | **Best: +$92.55/day, 44.7% day-WR** — most underexploited GOOD archetype | Structurally blocked — needs a level touch, rarely fires on pure trend | Thin: `bollinger_squeeze` 51-65 fills, `vwap_reclaim_failed_break` 3-11 fills; `vix_regime_dayside` unmeasured (no harness) | `trend-day-continuation` **KILLED 16/16** — non-level vocabulary does not close this gap |
| **range** (148 total, 90 sit-out = 60.8%) | 2nd-best: +$45.33/day, 39.7% day-WR | Best win-day archetype when it fires (48% of win-day volume) | Heaviest coverage: `bollinger_squeeze` 81-107 fills, `double_bottom_base_quiet` 52 fills (but negative EV) | `range-day-fade` **KILLED 16/16** — 2nd independent range-entry-family failure (range-pingpong was the 1st, per `EDGE-MATRIX-FULLHIST-2026-07-23.md`) |
| **chop** (136 total, 95 sit-out = 69.9%) | **Only net-losing archetype: -$43.83/day, 12.2% day-WR** | Active bleeder — trades 30% of chop days and loses on nearly all of them | Fires here too (`bollinger_squeeze` 62-82, `vwap_reclaim_failed_break` 8-29, `double_bottom_base_quiet` 28) — coverage without validated edge | `day-archetype-gate` — directionally clean (16/16 cells positive pnl-lift, real chop-detection) but **KILLED on day-majority** (see §1B); `class-conditional-exits` B1/C1 also chop-conditioned, both non-ship |
| **high VIX** (35 total, 0 sit-out counted as coverage — 0% ever traded) | Unmeasured (never fires) | Fully gated by `vix_bear_hard_cap=23.0` + `block_elite_bull` — by design | Untested | Not a cook target — correctly out of scope |

### 2.2 Combined $/day and days-covered — ESTIMATE, not a measured portfolio replay

**No day-level union harness exists.** Every lane tonight (and the extra-lanes-fullhist harness)
ran as an **isolated single-strategy replay** — none of them modeled what happens when two setups
would want to fire the same underlying move on the same day, or account for the one-position-at-a-time
constraint the real engine enforces. Naively summing each lane's own "days covered" produces
**153.7% of the 386-day population** (141 ribbon + ~260 bollinger_squeeze + ~76 vwap_reclaim_failed_break
+ ~116 double_bottom_base_quiet, each independently extrapolated from its own tuning-day coverage
rate — math below) — mathematically impossible, which is itself the proof that heavy day-level
overlap exists and nobody has measured how much.

| Bound | Days covered | $/calendar-day | Basis |
|---|---|---|---|
| **Floor (measured)** | 36.5% (141/386) | **+$13.09** (measured) | RIDE_THE_RIBBON alone — the only number in this section that is actually measured, not estimated |
| **Naive ceiling (unmeasured, ignores concurrency)** | mathematically >100%, capped | **+$19.82** | Ribbon $5,064.75 + 3 live-armed extra-setups' own baseline-cell tuning+heldout totals summed with zero overlap/concurrency correction (bollinger_squeeze +$4,404.23, vwap_reclaim_failed_break +$1,686.12, double_bottom_base_quiet **-$3,504.32**) |
| **Best-effort estimate (this doc, not measured)** | **~50-70%**, point estimate ~60% | **~$15-18/calendar-day** | Splits the difference given known high overlap (bollinger_squeeze/ribbon both concentrate on range+chop days) and known dead zones (chop's 95 sit-out days and all 35 high-VIX days are essentially untouched by any live setup per the anatomy's own qualitative fill evidence) |

**Either bound is nowhere near the $100-200/day FOCUS-DOCTRINE goal.** Even the naive, likely-
overstated ceiling of $19.82/calendar-day is ~10-13x short. Median $/trading-day for the COMBINED
portfolio is **unmeasurable from tonight's artifacts** — only the ribbon-alone median (-$63.00) is
known. Per FOCUS-DOCTRINE §3 ("day-consistency over total P&L"), this median is the single most
important missing number in the whole rig right now, and no lane tonight produced it for anything
but the core engine alone.

**Missing instrument, flagged per standing doctrine (repeated question = missing instrument):** a
day-level portfolio union/concurrency harness — walk all 6 live setups + RIDE_THE_RIBBON through
ONE shared day loop with the real one-position-at-a-time gate, so "days covered," "$/day," and
"median $/trading-day" can be measured once instead of estimated per-lane. This is the highest-
leverage next build, ahead of any new entry-signal search.

---

## 3. RANKED VERDICTS — FOCUS-DOCTRINE order (day-consistency first)

1. **`class-conditional-exits` (A6)** — the night's only structurally sound near-miss. A6
   (TRENDLINE-tier premium stop -20%→-12%, chandelier trail 15%→10%) is the ONLY 4/4-gate cell
   across all 83, with the best day-win-rate of the night (67.4% vs baseline 34.0%) on n=95 real
   fills, held-out positive (+$100.45). Fails only the portfolio-wide multiple-comparison bar
   (q=0.31). **Verdict: ACCRETE, not ship** — needs either more independent real fills or a
   standalone frozen pre-reg testing ONLY this cell (not embedded in a 13-cell grid) to get a fair
   single-test p-value.
2. **`day-archetype-gate`** — clean, construct-valid classifier (real chop-day detection, 62-79%
   precision per its own disclosure) that is a **correct KILL per FOCUS-DOCTRINE's own ranking**:
   it buys total $ by trading fewer, richer, LESS consistent days (day_wr -1.4pts), the literal
   opposite of "make money most days." A well-designed negative result, not a near-miss.
3. **`trendline-family-refinement`** — one actionable exclusion signal (STACKED-ribbon + AM-window
   TRENDLINE entries: p=0.0, -$705.60, reliably bad) sitting inside an otherwise too-thin dataset
   (19 MIXED-ribbon trades total in 18.5 months). **Verdict: ACCRETE** the MIXED bucket, consider
   a small dedicated follow-up pre-reg on the AM-STACKED exclusion alone (n=8 is thin even for a
   p=0.0, worth a second independent look before treating as settled).
4. **`extra-lanes-fullhist`** — the real value tonight is the **harness itself** (closed a
   measurement hole that's existed since the extra setups went live), not any single cell.
   Confirms `gap_and_go` correctly stays WATCH-only and surfaces a genuine audit finding:
   `double_bottom_base_quiet` is live-armed today with -$3,504.32 full-history combined P&L.
   **Verdict: flag for orchestrator re-audit**, not a cook-lane decision.
5. **`trend-day-continuation`** — clean 16/16 kill. Important negative result: the trend
   archetype's best-in-class economics (+$92.55/day) and worst coverage (60.8% sit-out) remain
   unclosed after a genuinely different, non-level attack vocabulary. This raises confidence the
   bottleneck really is RIDE_THE_RIBBON's level-touch requirement, not a tunable knob on top of it
   — the next attempt on `trend`, if any, needs a structurally different idea, not another variant
   of opening-range-hold/ribbon-persist.
6. **`range-day-fade`** — cleanest kill of the night, 16/16, no nuance. Second independent
   range-entry-family failure (after range-pingpong). **Range needs zero further entry-side R&D**
   — whatever coverage range gets should come from the already-live extra-setups or exit tuning,
   never a new range detector.

---

## 4. SHIP CANDIDATES / ACCRETE LIST / DEAD LIST

### Ship candidates: **NONE**

Zero of tonight's 83 cells clear both the lane's own 4-gate ship bar and the portfolio-wide
BH-FDR correction. This confirms the `survivors: []` input to this task rather than contradicting
it. Nothing in this section wires anything live — per standing doctrine, that decision belongs to
the orchestrator, never to this synthesis doc, and there is nothing here that clears the bar for
that conversation to even start.

### Accrete list (keep gathering evidence, no live wiring, no params.json edits)

| Candidate | What it needs |
|---|---|
| A6 (class-conditional-exits: TRENDLINE stop -12%/trail 10%) | Independent re-test — either accrete more real TRENDLINE-tier fills and re-run the same cell alone in a dedicated pre-reg (not inside a 13-cell grid), or wait for the next kitchen cycle's held-out window to grow and re-check q. |
| trendline-family-refinement MIXED-ribbon bucket | More data — only 19 trades in 18.5 months. Not actionable yet either direction. |
| trendline-family-refinement AM-STACKED exclusion | n=8 despite p=0.0 — worth a standalone confirmatory pre-reg before treating as a settled exclusion rule. |
| day-archetype-gate compression classifier | Repurpose as a MONITOR/dashboard flag (surface "compressed morning" to J's own discretion) rather than an auto-gate — it's construct-valid, just wrong-shaped for an automatic skip/half-size action. |
| bollinger_squeeze, vwap_reclaim_failed_break (already live) | No action — both show positive-but-not-yet-significant full-history economics; continue accruing real fills, re-test next kitchen cycle. |

### Dead list (do not re-cook)

- **range-day-fade** — 16/16 killed; 2nd independent range-entry-family failure. Range gets zero further entry-side R&D.
- **trend-day-continuation** — 16/16 killed; non-level trend vocabulary does not fix the level-touch bottleneck.
- **gap_and_go** — reconfirmed correctly WATCH-only (both cells net-negative, 0/4 gates).
- **class-conditional-exits C-group** — explicitly non-causal/diagnostic by the lane's own pre-reg design; structurally not gate-eligible regardless of q.
- **double_bottom_base_quiet at its current live baseline config** — this is an audit flag, not a kitchen kill (it's already live, not a candidate) — see §1C and §3.4.

---

## 5. THE 3-SENTENCE ANSWER TO "WHEN MONEY MOST DAYS"

**Not yet, and not from tonight's cook:** the live engine alone wins on roughly 12.4% of ALL
trading days (48/386) and loses on the median day it even fires (-$63), and every one of tonight's
6 attempts to close that gap either killed outright on the day-consistency bar (`day-archetype-gate`,
`range-day-fade`, `trend-day-continuation`) or produced a genuinely promising signal
(`class-conditional-exits` A6, 67.4% day-win-rate) that a full-night multiple-comparison correction
can't yet certify as more than noise. The one thing that DID survive tonight cleanly is a process
lesson, not a new strategy: stop admitting bare single-trigger TRENDLINE-tier rejections into a
wide/stacked ribbon (the one place a signal hit p=0.0 tonight, and TRENDLINE tier is already 65%
of all volume at a losing 19.4% win rate) while the two genuinely positive-but-unproven live extra
setups (`bollinger_squeeze`, `vwap_reclaim_failed_break`) keep accruing real fills. Given even the
naive, likely-overstated combined ceiling for everything currently live tops out around
$15-20/calendar-day against the $100-200/day goal, "most days" isn't a knob-tuning problem — it
needs either a genuinely new entry family for the trend archetype (best economics, worst coverage,
and now twice unsuccessfully attacked) or the currently-missing day-level portfolio harness to even
measure whether what's already live is closer to that goal than tonight's isolated numbers suggest.

---

## Disclosures

- BH-FDR at q≤0.10 across all 83 cells is this doc's own computation, not any lane's — every
  individual lane's own within-lane q-value (q(BH-13), q(BH-16), q(BH-12)) is reported verbatim in
  its own source file and remains correct for that lane's own narrower comparison; this doc adds
  the portfolio-wide correction on top, it does not replace or invalidate the lane-local numbers.
- §2.2's combined $/day and days-covered figures are explicitly labeled ESTIMATE — no day-level
  union/concurrency harness exists yet to measure the real combined portfolio. Treat the $15-18/day
  and ~50-70%-days-covered figures as bounded guesses with the stated floor/ceiling, not measurements.
- All per-lane $ figures are TUNING-scope unless marked "(combined)" or "held-out" explicitly —
  consistent with each lane's own held-out-day discipline (heldout sets frozen before any grid
  cell was computed, per each lane's own pre-reg).
- This doc performed no new backtest run, no live wiring, no params.json edits, no commits to any
  trading-path file, and placed no orders. Pure read/join/aggregate over the cited JSON/MD sources.
