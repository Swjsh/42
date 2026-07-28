# REGIME-CONDITIONING-RESLICE — 2026-07-28

**VERDICT: 0 candidates survive / 178 slices tested (161 BH-eligible) / BH critical p-threshold = none (nothing survives q≤0.10 correction).** The unconditional kills stand under J's own lens. That is the reportable answer to J's question — but the run also found 7 near-miss slices that pass every gate except the multiplicity correction, which is exactly the manufactured-false-positive risk the pre-reg warned about, and is worth J seeing.

Pre-reg (frozen before any run): [`analysis/recommendations/prereg-regime-conditioning-2026-07-28.json`](../recommendations/prereg-regime-conditioning-2026-07-28.json) (commit `1e3dc624`). Tool: [`backtest/tools/regime_reslice_2026_07_28.py`](../../backtest/tools/regime_reslice_2026_07_28.py). Guard tests: [`backtest/tests/test_regime_reslice_2026_07_28.py`](../../backtest/tests/test_regime_reslice_2026_07_28.py) (13/13 green). Full machine output: [`REGIME-RESLICE-2026-07-28.json`](REGIME-RESLICE-2026-07-28.json).

---

## J's question, answered with data

> "Are you sure that you're not trying to apply the same strategy every day? ... Just because it failed every day doesn't necessarily mean it should be a kill."

He's right that every variant killed this week (score ladder, structure-shift, zone-width bands) was tested **unconditionally** — one rule, applied at every trigger, regardless of market state. This run took every stored per-trade record from that graveyard and asked: *is there a morning-knowable regime bucket where any of these is consistently positive?*

**Answer: no bucket clears the bar once you correct for how many buckets were checked.** Several buckets *look* tempting in isolation (positive, majority of days won, survives dropping the best trade, n≥25) — but none survive Benjamini-Hochberg FDR at q≤0.10 across the full 161-slice surface. This is the difference between "regime conditioning never works" (not what this run shows) and "none of THESE specific graveyard variants have a regime pocket strong enough to distinguish itself from noise, once you're honest about how many pockets you checked" (what this run shows).

---

## Method (as frozen, no deviations)

Purely **descriptive** — every trade consumed here was already computed by an earlier, already-committed replay tool. No new replays, no new variants, no re-optimization, no parameter tuning.

**10 variants** sliced (the pre-reg's 6 bullets expand to 10 distinct trade populations — ladder floors 7/8/9 are 3 separate lanes, structure-shift standalone is K=3 and K=2 separately, zone bands are 10c and 25c separately):

| Variant | Source (persisted per-trade detail) | n |
|---|---|---:|
| `ladder_floor_7` | `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json` → `lanes.7.trades` | 1,538 |
| `ladder_floor_8` | same file → `lanes.8.trades` | 725 |
| `ladder_floor_9` | same file → `lanes.9.trades` | 332 |
| `ladder_subset_9_confluence_htf` | `analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.json` → `primary_trades` | 109 |
| `structure_shift_standalone_K3` | `analysis/recommendations/structure-shift-replay-2026-07-28.json` → `K=3_primary.trades` | 1,668 |
| `structure_shift_standalone_K2` | same file → `K=2_sensitivity.trades` | 1,670 |
| `structure_shift_in_cascade_delta` | `analysis/recommendations/structure-shift-cascade-ab-2026-07-28.json` → `changed_trades` (delta only — see caveat) | 20 |
| `zone_band_10c_marginal` | `analysis/deep-research/ZONE-WIDTH-2026-07-28.json` → `cells.10c.marginal_trades` (net-new only — see caveat) | 13 |
| `zone_band_25c_marginal` | same file → `cells.25c.marginal_trades` | 19 |
| `min_triggers_bear2` | reconstructed: `engine-fullhist-replay-2026-07-23.json` baseline − `removed_trades` + `added_trades` (see caveat) | 74 |

**4 regime axes** (morning-knowable only, per the pre-reg's frozen no-look-ahead rule):

- **gap_state** (up/down/flat) — from `analysis/edge-matrix/day-inventory-extended.json`'s `gap_pct` for the trade's own day.
- **prior_day_type** (trend/range/chop) — from the same file's `day_type` for the **prior** trading day (never the trade's own day, which is exactly the L118-121/C22 backward-looking-classifier trap the pre-reg named explicitly).
- **vix_band** (low/mid/elevated/high) — from the VIX 5-minute bar closing **at or before** the trade's own `entry_time_et`, bisected so a future bar can never be selected. Verified DST-aware (winter rows carry `-0500`, summer rows carry `-0400` — unlike the SPY 5m cache's known fixed-`-04:00`-year-round quirk, C6/`project_dst_frame_artifact_2026_07_02`; guarded by `test_vix_bars_are_dst_aware_not_fixed_offset`).
- **entry_hour** (09:xx … 15:xx) — hour of `entry_time_et`.

**1 axis excluded, disclosed, not fabricated: `premarket_range_pct`.** No repo-wide historical premarket high/low dataset spans the full 2025-01-02..2026-07-27 window — only current-day snapshots exist (`eod-deep-*.json`, swarm state). Deriving it from raw 5-minute bars under this run's time budget would have meant hand-rolling a new premarket-range computation across 389 trading days and risked exactly the DST/frame look-ahead bug this project has already been burned by once. The pre-reg explicitly sanctions excluding an axis with no honest source rather than guessing — taken.

**Slice surface:** 10 variants × 4 axes × (up to 4-7 buckets each) = **178 total slices** (158 in real regime buckets; 20 in `unknown`/`unclassified` data-quality buckets, reported but never candidate-eligible). **161 slices had a computable p-value** (one-sample one-sided t-test, `H1: mean pnl > 0`, requires n≥2 and non-degenerate variance) and form the Benjamini-Hochberg correction surface.

**Candidate gate (frozen, unchanged):** n≥25 **and** positive aggregate **and** day-majority **and** survives-drop-best **and** BH-significant at q≤0.10 across the full 161-slice surface.

---

## Data-quality caveats (disclosed per pre-reg instruction, nothing guessed)

1. **`structure_shift_in_cascade_delta` — only the delta is persisted, not the full treatment book.** The cascade A/B file itemizes `changed_trades` (13 ADDED + 7 PREEMPTED = 20) but only aggregate `n_trades`/`total_pnl` for `control`/`treatment` — no per-trade array for the full book. Correctly sliced by **`contribution`** (the net dollar effect of running this variant instead of control on that trade-slot), not `dollar_pnl` (which for PREEMPTED rows is the *control* trade's own outcome — a field-confusion trap caught and fixed during this run; verified `sum(contribution) == headline.delta_total` exactly, −$46.00). n=20 is below the n≥25 floor even in full aggregate, so this variant cannot produce a candidate at any regime granularity — descriptive-only.

2. **`zone_band_10c_marginal` / `zone_band_25c_marginal` — only net-new trades are persisted, not the full book under the wider band.** `marginal_trades` (net additions vs the 0c control) are itemized; `displaced_trades` (control trades the wider band crowds out) are a separate itemized list, deliberately excluded here — mixing "what this variant adds" with "what it removes" under one regime label would conflate two different populations. `full_book_stats` (the complete holding, n=167/163) has no per-trade array and isn't reconstructable without the 0c control's own itemized list, which isn't persisted either. n_marginal (13, 19) is below n≥25 even in full aggregate — descriptive-only.

3. **`min_triggers_bear2` — reconstructed, and a $36 internal-arithmetic discrepancy was found and disclosed.** The full 74-trade variant population isn't directly persisted (only `removed_trades`/`added_trades` deltas vs the 190-trade baseline). Reconstructed as `(baseline − removed) + added`; join verified exact (all 120 removed trades matched 1:1 against baseline on `(date, entry_time_et, symbol, side, qty)`, 0 unmatched, no duplicate keys). The reconstruction total ($7,596.80) matches the source file's **own component fields** exactly (`baseline_total − removed_trades_pnl + added_trades_pnl = 7,596.80`), but the same file's separately-stated `headline.variant_total` reads $7,632.80 — a $36.00 discrepancy **within that file's own numbers**, not introduced here. Used the internally-consistent reconstruction; flagging the source anomaly rather than silently picking one number. Out of scope to chase further (descriptive re-slice, no new replays).

   Note: `min_triggers_bear2` is **not a graveyard kill** — the pre-reg lists it as "already staged," and only asks for it to be re-sliced by regime too, for the same informational purpose. Its own already-positive aggregate ($7,596.80 / 74 trades, p=0.007) is real and separately staged; it's included here for completeness, not as a kill under review.

---

## Full candidate list

**Empty.** Zero slices satisfy all five frozen gates.

---

## The 7 near-misses (4-of-5 gates, killed only by multiplicity correction)

These pass n≥25, positive aggregate, day-majority, and survives-drop-best — everything **except** BH significance. This is precisely the manufactured-false-positive risk named in the pre-reg's `multiplicity_discipline` clause, caught by the very control it prescribed:

| Variant | Axis | Bucket | n | Total $ | Per-trade | p (one-sided) | BH crit @ rank | BH-sig? |
|---|---|---|---:|---:|---:|---:|---:|:---:|
| `min_triggers_bear2` | prior_day_type | range | 33 | +5,628.00 | +170.55 | 0.00637 | 0.00062 (rank 1/161) | **NO** |
| `structure_shift_standalone_K3` | gap_state | down | 650 | +5,420.60 | +8.34 | 0.2112 | needed ≤0.0037 | NO |
| `structure_shift_standalone_K2` | vix_band | elevated | 276 | +3,470.05 | +12.57 | 0.2354 | needed ≤0.0043 | NO |
| `structure_shift_standalone_K2` | prior_day_type | range | 618 | +4,228.75 | +6.84 | 0.2429 | needed ≤0.0050 | NO |
| `structure_shift_standalone_K3` | vix_band | elevated | 277 | +3,302.25 | +11.92 | 0.2448 | needed ≤0.0056 | NO |
| `structure_shift_standalone_K3` | prior_day_type | range | 627 | +3,889.35 | +6.20 | 0.2605 | needed ≤0.0062 | NO |
| `structure_shift_standalone_K3` | vix_band | mid | 1,162 | +3,022.35 | +2.60 | 0.3340 | needed ≤0.0068 | NO |

Even the single best p-value in the entire 161-slice surface (0.00637) needed to beat 0.00062 to survive rank-1 BH correction and missed by 10×. The structure-shift standalone rows (K3/K2, gap-down / VIX-elevated-or-mid / prior-day-range) recur across multiple axes — consistent with those buckets simply containing more of the trades, not with a strong, axis-specific edge; none individually clears noise.

---

## Honest diagnostic: least-bad / worst regime bucket per variant

**Descriptive only — none of these are candidates, several have thin n. Never proposable, never armable off this table.**

| Variant | Least-bad bucket | n | $/trade | Worst bucket | n | $/trade |
|---|---|---:|---:|---|---:|---:|
| `ladder_floor_7` | entry_hour 10:xx | 314 | −4.12 | gap_state flat | 48 | −50.50 |
| `ladder_floor_8` | vix_band low | 14 | +11.34 | gap_state flat | 21 | −93.41 |
| `ladder_floor_9` | entry_hour 15:xx | 10 | +47.15 | entry_hour 14:xx | 53 | −81.87 |
| `ladder_subset_9_confluence_htf` | entry_hour 09:xx | 4 | +480.81 | gap_state flat | 2 | −294.00 |
| `structure_shift_standalone_K3` | entry_hour 10:xx | 389 | +24.32 | vix_band low | 111 | −28.64 |
| `structure_shift_standalone_K2` | entry_hour 10:xx | 400 | +21.88 | vix_band low | 112 | −29.09 |
| `structure_shift_in_cascade_delta` | gap_state flat | 2 | +129.30 | entry_hour 14:xx | 2 | −523.20 |
| `zone_band_10c_marginal` | gap_state flat | 1 | +442.50 | vix_band elevated | 1 | −145.80 |
| `zone_band_25c_marginal` | entry_hour 14:xx | 4 | +100.75 | entry_hour 11:xx | 1 | −330.00 |
| `min_triggers_bear2` | gap_state flat | 3 | +380.68 | entry_hour 15:xx | 1 | −50.00 |

Worth a second look for eventual, **separately pre-registered**, purely observational follow-up (not action): `structure_shift_standalone_K3`/`K2` both show their least-bad pocket at the 10:xx entry hour (n=389/400, +$9,460/+$8,754 total, positive but not BH-significant per above) and their worst at `vix_band=low` (n=111/112, ~−$3,200 total each) — a directionally consistent pattern across two closely related variants, but not statistically distinguished from noise at this sample size once corrected.

---

## What this run does NOT establish

- **Nothing here is armable or even proposable.** A surviving slice would earn exactly one thing — its own fresh pre-registration on a frozen forward/held-out window, run separately. There were no surviving slices.
- The graveyard kills (score ladder, structure-shift standalone/cascade, zone-width bands) **stand**. Regime conditioning did not rescue any of them at the axes and buckets tested here.
- This does **not** prove regime conditioning is worthless in general — only that these specific catastrophic-margin losers didn't have a strong enough regime pocket to clear a properly corrected significance bar. The pre-reg's own framing was right: conditioning is more plausible for *marginal* unconditional results than for variants that lost by tens of thousands of dollars unconditionally (ladder floor 7: −$31,015 over 1,538 trades).
- The harness (`regime_reslice_2026_07_28.py`, 13 green guard tests) now exists and is reusable for exactly that future case — a marginal (not catastrophic) unconditional result, tested for regime dependence before being killed outright.

---

## Files

- Tool (new): [`backtest/tools/regime_reslice_2026_07_28.py`](../../backtest/tools/regime_reslice_2026_07_28.py)
- Guard tests (new, 13/13 green): [`backtest/tests/test_regime_reslice_2026_07_28.py`](../../backtest/tests/test_regime_reslice_2026_07_28.py)
- Machine output (new): [`analysis/deep-research/REGIME-RESLICE-2026-07-28.json`](REGIME-RESLICE-2026-07-28.json)
- Pre-reg (frozen, unmodified): [`analysis/recommendations/prereg-regime-conditioning-2026-07-28.json`](../recommendations/prereg-regime-conditioning-2026-07-28.json)
