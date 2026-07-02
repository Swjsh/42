# Phase B — J-EDGE DEEP MATRIX: pre-registered design (FROZEN before grinding)

> Written + committed **BEFORE** the grinder runs (discipline contract). Anything not
> registered here is exploratory and cannot change the verdict.
>
> ## ⚠ BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1
> Every dollar figure this program produces comes from the same smile-less, spread-less
> Black-Scholes path model as E2 (`backtest/lib/pricing.py`, IV = day's VIX open / 100,
> r = 4%, expiry 16:00 ET). Numbers RANK hypotheses in-era; they are NEVER a promotion
> gate, NEVER a live P&L forecast. Survivors become Phase-C port specs for the 2025-26
> OPRA real-fills battery — nothing arms from here.

## Question

Within J's 567 closed 2021-23 family episodes ("his entry moments + direction"), which
combination of {exit ladder × strike selection × sizing × entry-context filter} carries
in-era edge that survives an honest train/test + FDR protocol? (E2 already showed the
v15 ladder + ATM + no-adds flips the book positive; this maps the WHOLE neighborhood.)

## Population & machinery (reused, not rebuilt)

- Episodes: `analysis/j-webull/trades-normalized.csv` join onto the fill-level rebuild
  from `scripts/e2_e5_replay.py::build_episodes_with_fills` (self-checks: 567 episodes,
  −$12,885.00 total, asserted).
- Replay core: same conventions as E2 — entry priced at the close of the last COMPLETED
  SPY 5m bar ≤ entry tick (C6-causal); path = subsequent 5m bar closes, last path bar
  starts 15:45 ET (closes 15:50); SPX/SPXW spot = 10×SPY, XSP = 1×SPY; IV = entry day's
  ^VIX OPEN (fallback prior close), constant intraday; BS premium floor $0.05 —
  below = unpriceable, dropped + counted per cell (C7).
- Drops carried over from E2: no_ctx (25), no_path_bars (3), plus per-strike unpriceable.

## Train / test split (fixed BEFORE grinding)

- **Train:** entry_ts < 2023-01-01 (2021-06..2022-12; ~471 ctx-ok episodes).
- **Test:** entry_ts ≥ 2023-01-01 (2023-01..2023-10; **71 ctx-ok episodes pre-drop**).
- All ranking happens on train ONLY. The test year is evaluated ONCE, for K ≤ 25
  pre-selected cells, then Benjamini-Hochberg FDR (α = 0.1) across those K p-values.
- **Honest capacity note, registered up front:** with only 71 test episodes, the
  mandated per-cell n_test ≥ 30 gate is mechanically reachable ONLY by broad filters
  (all = 71, calls = 43, VWAP-aligned = 50 pre-drop). Narrow filters (at-level, windows,
  DOW, pairs) will be ground and reported on the train side but CANNOT become survivors
  this pass — that is the design, not a bug.

## The matrix

**Exit axis (96 combos):** stop {−8%, −20%, −35%, −50%} × TP1 {+30% sell 2/3,
+75% sell 2/3, +150% sell 80%, none} × trail {none, chandelier: arms at +5% favor,
exits at prem ≤ 0.85 × premium-HWM} × time-stop {60m, 120m, EOD 15:50}.

Walker semantics (per 5m bar close, in this fixed order):
1. **Stop** (pre-TP1 only; full position) at ret ≤ stop.
2. **Chandelier** (if trail on; applies to all open fraction incl. runner): HWM update,
   arm at ret ≥ +5%, exit at prem ≤ 0.85 × HWM.
3. **TP1**: sell tp1_frac at bar prem; remainder = runner with **breakeven floor**
   (post-TP1 bars: exit runner at ret ≤ 0). Matrix cells have NO fixed runner target
   (runner rides until chandelier / breakeven / time-stop).
4. **Time-stop**: 60m/120m measured from entry-bar close t0 (bars with close ≤ t0+X;
   if none, exit at first path bar); EOD = E2's 15:50 convention. Remainder exits at
   the last in-window bar close.
- Non-0DTE episodes (15%) force-flattened same day (machine's rule; disclosed as in E2).

**Strike axis (5):** {his actual, ATM, ITM1, ITM2, OTM1}. Step = $1 SPY/XSP, $5
SPX/SPXW, offset from `atm_strike(spot0)`; ITM = strike in-the-money direction of the
right, OTM opposite. Unpriceable (BS prem < $0.05) drops counted per cell. Registered
caveat: percent-exits on "his actual" strikes ride on BS entry premia that misprice his
deep-OTM lottos (E2 calibration: median BS/actual = 0.222) — his-strike cells are the
noisiest and their drops are adversely selective.

**Size axis (3):** {first-fill cap (J's first fill qty, no adds), fixed 1 lot, fixed
3 lots}. Sizing changes $ not signal — fixed-1 and fixed-3 have identical t-stats, so
they collapse to one signal class for ranking (fixed-1 ranked; fixed-3 reported = 3×).
Per-contract expectancy reported for every cell.

**Filter axis (37 = 16 singles + 21 pairs, ≤ 2 deep, all entry-time-causal):**
- Singles: all · direction C · direction P · at-level (|nearest_level_dist_pct| ≤ 0.1)
  · VWAP-aligned (bull&above / bear&below) · window {open 09:30-10, morning 10-11,
  midday 11-14, late 14-16 — E3's boundaries} · DOW ×5 · first-test / retest
  (at-level AND no/any prior completed bar today touching the level within 0.1%,
  strictly before the entry bar — counts as 2-deep composite).
- Pairs (families {direction, at-level, aligned, window} only; DOW and
  first-test/retest excluded from pairing to cap fishing): dir×at-level (2),
  dir×aligned (2), dir×window (8), at-level×aligned (1), at-level×window (4),
  aligned×window (4).
- **E6 features:** `analysis/j-webull/E6-structure-read/results.json` will be checked
  once, immediately before the grind fires. If present, E6's top pre-registered
  features join as additional single filters (cited); if absent, proceed without (its
  REGISTRATION.md exists but no results at design time).

Total cells: 96 × 5 × 37 × 3 = **53,280** (35,520 distinct signal cells after the
fixed-size collapse).

## Selection protocol (frozen)

1. Grind all cells on TRAIN only. Full grid persisted.
2. **Eligibility** (train + counts only — test P&L untouched): n_train ≥ 60 ·
   train mean > 0 · train total with top-3 winners dropped > 0 ·
   **n_test ≥ 30 by entry-time filter membership count** (this uses zero outcome
   information — filters are functions of pre-entry context only).
3. **Rank** eligible cells by train t-statistic (mean / (sd/√n)) of per-episode P&L.
4. **Diversity caps** (anti-clone): ≤ 3 cells per (filter, strike) pair, ≤ 10 per
   filter. Take top **K ≤ 25**.
5. Evaluate the K cells on TEST **once**: per-episode P&L → one-sided one-sample
   t-test (H1: mean > 0) → p-values; 10k-bootstrap P(sum ≤ 0) reported alongside.
6. **BH FDR α = 0.1** across the K p-values → q-values.
7. **Survivor** = q ≤ 0.1 AND n_test ≥ 30 (realized, post-drop) AND test total with
   top-3 dropped > 0 AND both chronological halves of test positive.
8. **Null diagnostic (reported, not a gate):** each top-K cell re-run on test with
   OPPOSITE direction at ATM (E2's null construction). A survivor whose test total
   does not beat its null is flagged `null_dominated` — per E2, the frictionless-BS
   ladder harvests ~+$76/tr of convexity that real spreads would eat.

## Sanity anchors (must reproduce before results count)

E2 variant (a) (his strike) and (b) (ATM) exact configs — TP1 +30% sell 0.80, runner
target 2.5× entry with breakeven, cat −50%, EOD — re-run through THIS grinder's
generalized walker over the full population must match
`E2-machine-management-replay.json` machine totals and n within $2 / 0 episodes.
Mismatch = engine bug → no results published.

## Verdict ladder (registered)

- **SURVIVORS_FOUND** — ranked list; each ships a Phase-C port spec (exact detector
  definition + exit + size) for the 2025-26 OPRA battery.
- **TRAIN_ONLY_MIRAGE** — top-K all die on test.
- **NOTHING_POSITIVE** — no eligible train-positive cells at all.

## Outputs

`analysis/j-webull/PHASEB-matrix/`: this file · `matrix_grinder.py` · `results.json`
(funnel, anchors, top-K test table, survivors) · `train-grid.csv.gz` (full cell grid)
· `RESULTS.md` (funnel + survivor table + port specs).

Fixed seeds: bootstrap rng = 42. Runtime budget: single process, no workers needed
(~260k path walks ≈ minutes).
