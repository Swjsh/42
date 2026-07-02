# E6 — J structure-read pre-registration (FROZEN 2026-07-02 ~02:00 ET, BEFORE any outcome computation)

> **Discipline contract:** this file is committed BEFORE any feature↔outcome correlation is
> computed. The feature set, score construction, split, single evaluation metric, and accept
> thresholds below are frozen. The test year is evaluated ONCE. Anything not registered here
> is exploratory and cannot change the verdict.

## Hypothesis

J's direction alpha (59.2% null-controlled, E2 verdict MANAGEMENT_WAS_THE_LEAK) is carried by
price BEHAVIOR at levels (rejection/reclaim/structure state) readable from completed SPY 5m
bars at his entry timestamp — not by the crude coordinate fingerprint (level distance + VWAP
side + clock) that went DRY in E1.

## Population

- Source: `analysis/j-webull/trades-normalized.csv` (567 closed SPX/SPY-family episodes).
- Include: `is_family=True`, `closed=True`, `ctx_ok=True`, `bias ∈ {bull,bear}`, `pnl` present.
- Bars: `analysis/j-webull/cache/spy_5m_2021-06-01_2023-10-31.csv` (Alpaca IEX raw), RTH bars
  only (09:30 ≤ bar start < 16:00 ET), same as `build_normalized.py`. Daily levels from
  `cache/spy_daily_2021-06-01_2023-10-31.csv` shifted one day (PDH/PDL/PDC).
- **Causality (C6):** every feature uses only 5m bars whose window CLOSED at-or-before the
  entry tick (`bar_close_ts ≤ entry_ts`). b0 = the last such bar. B = today's completed RTH
  bars through b0. Asserted in code.
- **Early-entry drop (registered):** episodes with fewer than 3 completed RTH bars before
  entry (entry before ~09:45 ET) are DROPPED — structure cannot be read from <3 bars of tape.
  This removes much of J's 09:30 bucket (his worst window, −$35.9/tr); the studied population
  is therefore "J past the open", disclosed in RESULTS.
- **Exit join (outcome only, not a feature):** SPY spot at exit = close of the last completed
  RTH bar with `bar_close_ts ≤ exit_ts` (any date ≤ cache end). Episodes with no such bar
  strictly after the entry bar are dropped.
- All drops counted and disclosed per C7.

## Outcome labels (never used in feature construction)

- `dir_ok` = 1 if (bull AND spy_exit > spy_entry) OR (bear AND spy_exit < spy_entry), else 0
  (ties = 0). spy_entry = b0 close (the CSV's `spy_px`).
- `pnl` = actual WeBull episode P&L from the CSV.

## Reference level L

Nearest of {PDH, PDL, PDC} (prior day RTH daily bar) to b0.close by absolute % distance —
identical to `build_normalized.py`'s `nearest_level`. Sanity assert: recomputed choice matches
the CSV's `nearest_level` on ≥99% of joined rows. Episodes with no prior-day daily row drop.

## Registered features (10 — frozen)

All computed from B (completed bars only), L, the RTH-continuous EMA series, and the running
session VWAP (both exactly as `build_normalized.py` computes them). "Favorable side of L" =
close > L for bull, close < L for bear. NaN/insufficient-history feature values are imputed to
the TRAIN mean (i.e., z=0) — never dropped after the ≥3-bar gate.

| # | Name | Exact definition |
|---|---|---|
| F1 | `wick_favor` | Entry bar b0 rejection wick in trade direction: bull = (min(o0,c0)−l0)/(h0−l0); bear = (h0−max(o0,c0))/(h0−l0); 0 if h0==l0. |
| F2 | `level_sweep_favor` | 1 if any of the last 3 bars of B pierced L against the trade by ≥$0.05 and closed back favorable (bull: low < L−0.05 AND close ≥ L; bear: high > L+0.05 AND close ≤ L); else 0. (levels.py `_detect_swept_levels` semantics, direction-aware.) |
| F3 | `hold_bars` | Consecutive bars ending at b0 (cap 6) closing on the favorable side of L; 0 if b0 unfavorable. |
| F4 | `structure_align` | `crypto.lib.market_structure.analyze_structure(B, window=2)` trend: +1 if uptrend&bull or downtrend&bear; −1 if opposite; 0 if range/unknown. |
| F5 | `event_recency` | From the same read's `last_event` (BOS/CHoCH): s/(1+bars_ago) where bars_ago = (len(B)−1) − break_index and s=+1 if event direction matches bias else −1; 0 if no event. |
| F6 | `body_favor` | Signed entry-bar body: bull = (c0−o0)/(h0−l0); bear = (o0−c0)/(h0−l0); 0 if h0==l0. |
| F7 | `vwap_streak` | Signed count (cap ±12) of consecutive bars ending at b0 closing on the trade side of the running session VWAP (bull above / bear below); negative streak length if b0 is on the wrong side. |
| F8 | `touch_count` | Number of bars in B excluding b0 whose [low−0.15, high+0.15] range contains L (cap 10). First-test vs re-test freshness; direction-neutral, sign learned on train. |
| F9 | `ribbon_slope_favor` | spread(t) = (ema8/ema21 − 1)×100 on the RTH-continuous close series (ewm span 8/21, adjust=False, warm from cache start); slope = spread(b0) − spread(b0−3) (series-wise, cross-day allowed, 0 if <4 bars of history); bull = slope, bear = −slope. |
| F10 | `abs_level_dist` | \|(c0/L − 1)×100\| — the one coordinate control (E1's at-level fingerprint). |

## Score (frozen construction — no tuning, no iteration)

- On TRAIN only: z-standardize each feature (train mean/std; std=0 → feature excluded);
  weight w_k = Pearson correlation of z_k with `dir_ok` on train (point-biserial).
- `score = Σ_k w_k · z_k(x)` with train z-parameters applied unchanged to test.
- No refits, no feature selection beyond the frozen 10, no interaction terms, no peeking at
  test before the single evaluation.

## Split

- TRAIN: entry date ≤ 2022-12-31 (2021-06 .. 2022-12).
- TEST: entry date ≥ 2023-01-01. Evaluated ONCE with the frozen score.

## The single evaluation metric (primary)

Within TEST, rank by score; TOP quartile = highest-score ⌈n/4⌉ episodes, BOTTOM quartile =
lowest ⌈n/4⌉ (stable sort, ties broken by episode_id ascending).

- **PRIMARY: Δhit = hit_rate(top) − hit_rate(bottom)** on `dir_ok`.
- Secondary (confirmatory, directional only): Δpnl = mean pnl(top) − mean pnl(bottom).
- **Permutation p (seed 42, 1000 draws):** permute the (dir_ok, pnl) outcome pairs across
  test rows jointly, quartile membership fixed by score; one-sided
  p = (1 + #{Δhit_perm ≥ Δhit_obs}) / 1001. Same formula reported for Δpnl (secondary).

## Accept thresholds (verdict ladder — frozen)

- **SEPARATES:** test n ≥ 40 AND Δhit > 0 AND p(Δhit) < 0.05 AND Δpnl > 0.
- **WEAK:** Δhit > 0 but not all SEPARATES conditions met (p ≥ 0.05, or Δpnl ≤ 0, or test n < 40).
- **NO_SEPARATION:** Δhit ≤ 0. Stated plainly: J's read is not recoverable from 5m bars.

## Registered sanity checks (run before the test eval; failures void the study, not the verdict rung)

1. Recomputed nearest_level matches CSV `nearest_level` on ≥99% of joined rows.
2. Overall direction hit-rate across all joined episodes reproduces TRAITS #3 (59.2% ± 2pp).
3. Code assertion: no feature bar has `bar_close_ts > entry_ts`.

Train-side quartile stats and per-feature train correlations are reported as DESCRIPTIVE only.

## Outputs

`analysis/j-webull/E6-structure-read/{REGISTRATION.md, RESULTS.md, results.json, scripts/e6_structure_read.py}`.

If SEPARATES: the follow-up (SPEC ONLY, not run) = port the top feature combo as detector
`J_STRUCT_LEVEL` into the 2025-26 OPRA battery per E1's harness shape.
