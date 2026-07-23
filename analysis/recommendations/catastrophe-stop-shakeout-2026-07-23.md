# Q1 -- Catastrophe-stop shakeout A/B (2026-07-23)

Generated 2026-07-23T16:38:55.089003. Runner: `backtest/tools/catastrophe_stop_shakeout_ab.py`. Pre-reg: `analysis/recommendations/catastrophe-stop-shakeout-prereg-2026-07-23.json`.

## TODAY's counterfactual -- Bold bold-2 SPY260723P00735000

Entry 11:29:25 ET @ $1.28 x5 -> catastrophe-stopped 11:56:05 ET @ $0.67 = **$-305.00 realized**.

- Max-favorable premium print AFTER the stop (real 1-min OPRA): $0.78 at 11:57:00 ET -> best-case counterfactual (sold at that exact print) = **$-250.00** (still a loss).
- Held to time-stop (15:40 ET): premium $0.12 -> **$-580.00**.
- Held to EOD (16:00 ET RTH close): premium $0.05 -> **$-615.00**.

**NOT a shakeout in hindsight -- max-favorable-after-stop ($0.78 at 11:57 ET, one minute after the exit) never approached breakeven let alone TP1; both the held-to-time-stop and held-to-EOD counterfactuals are WORSE than the actual catastrophe-stop exit. SPY bounced off the 11:30 ET low (735.21) and STAYED elevated (RTH close ~738.24, not the lower level implied by an assumed later-day reversal) -- the 735P decayed on theta/OTM drift, not a wick that reversed.**

**Control shape**: `{'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'runner_target_pct': 99.0, 'trail_pct': 0.15, 'profit_lock_arm_pct': 0.05, 'stop_mode': 'structure', 'catastrophe_stop_pct': -0.5, 'profit_lock_arm_scope': 'post_tp1'}`

Population: 151 total bear (BEARISH_REJECTION_RIDE_THE_RIBBON) trades, 2025-01-02..2026-07-22 (reused from engine-fullhist-replay-2026-07-23.json). Only 27 resolved stop_mode=='structure' (this axis's entire exposed population) -- the other 124 use premium_stop_pct=-0.20, untouched by any candidate here.

CONTROL total (structure-mode subset, n=27) = $+4,559.45. OOS held-out = last 6 trades (2026-06-25..2026-07-20).

## Descriptive shakeout stat (BEFORE any candidate gate -- pure description)

Of the 4 trades where the -50% catastrophe cap actually fired under CONTROL:
- Structure later confirmed the break by EOD: 0/4 (0.0)
- Option premium recovered back past the exit fill by EOD: 4/4 (1.0)
- Option premium reached the TP1 threshold (+100%) by EOD: 3/4 (0.75)

| date | symbol | entry premium | trigger_level | control pnl | structure confirmed by EOD | max premium after stop | recovered past exit | reached TP1 |
|---|---|--:|--:|--:|:--:|--:|:--:|:--:|
| 2025-06-05 | SPY250605P00595000 | 0.92 | 595.98 | $-230.00 | False | 4.04 | True | True |
| 2026-06-09 | SPY260609P00735000 | 2.6 | 738.1900024414062 | $-390.00 | False | 12.42 | True | True |
| 2026-06-17 | SPY260617P00745000 | 2.37 | 750.8286009873198 | $-355.50 | False | 5.74 | True | True |
| 2026-06-22 | SPY260622P00744000 | 1.21 | 746.1 | $-242.00 | False | 1.07 | True | False |

## Candidates

| id | catastrophe_stop_pct | n | control $ | candidate $ | agg delta | gate1 agg | gate2 days | gate3 drop-best1 | gate4 OOS-last25 | verdict |
|---|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|
| CAND-WIDE70 | -0.7 | 27 | $4,559.45 | $6,706.00 | $+2,146.55 | True | False | True | False | **CONTROL_HOLDS** |
| CAND-NOCAT | -0.99 | 27 | $4,559.45 | $8,185.50 | $+3,626.05 | True | False | True | False | **CONTROL_HOLDS** |

## Give-back accounting

| id | extra captured on beats | n beats | extra given back on losses | n losses | net |
|---|--:|--:|--:|--:|--:|
| CAND-WIDE70 | $+2,385.55 | 2 | $-239.00 | 2 | $+2,146.55 |
| CAND-NOCAT | $+3,626.05 | 4 | $+0.00 | 0 | $+3,626.05 |

## Disclosure: BH-FDR (alpha=0.10, 2 candidates)

| id | raw p | BH threshold | significant |
|---|--:|--:|:--:|
| CAND-WIDE70 | 0.10518 | 0.1 | False |
| CAND-NOCAT | 0.03377 | 0.05 | True |

## Reconciliation vs already-CONTROL-HELD stop studies

**trail-width-exit-2026-07-21**: held catastrophe_stop_pct constant at -0.50 across every candidate (control_shape dict printed in that study's own output: 'catastrophe_stop_pct': -0.5, unchanged in TRAIL-20/25/30, TP1Q-050/033, RIDE-BUNDLE) -- varied ONLY trail_pct/tp1_qty_fraction/tp1_premium_pct. Disjoint from this study's axis.

**structure-stop-reference-level-2026-07-20**: held catastrophe_stop_pct constant at -0.50 across REF-EXACT/REF-ZONE/REF-NONE -- varied ONLY the structure-stop's REFERENCE LEVEL (WHERE trigger_level is sourced from: trigger-exact vs zone-boundary vs none), never whether/how hard the catastrophe backstop bites. Disjoint from this study's axis.

**Conclusion**: This study's axis (catastrophe_stop_pct threshold, i.e. HOW WIDE the premium backstop is once already in structure mode) is genuinely disjoint from both prior NO-SHIP/CONTROL_HOLDS studies -- not a re-litigation. Restated with the actual run numbers in the companion .md regardless of which way this study's own verdict lands.

## Disclosed limitations

- This axis (catastrophe_stop_pct) only ever exposes the 27/151 bear trades that resolved stop_mode=='structure' at entry (rejection_level populated by the orchestrator entry layer). The other 124 trades use premium_stop_pct=-0.20 (untouched by any candidate here) -- their delta is exactly $0 by construction, excluded from the gate population to avoid diluting/hiding the real n.
- n_structure_mode=27 clears this codebase's own advisory evidence floor (15 events for a directional read, per late-entry-ceiling-review.json precedent), but the count of trades where a candidate can show ANY nonzero delta is strictly bounded by how many hit premium_stop under CONTROL (n=4) -- reported per-candidate; n=4 is FAR below the floor and is the real limiting sample size for this mechanism.
- ribbon_flip_back IS modeled (continuous RTH ribbon lookup, backward merge_asof, same construction as engine_fullhist_replay.py) -- unlike several prior real-fills studies that disclosed it OFF, this study inherits the fuller engine-fullhist-replay harness.
- C6 fill-mark convention (exit_manager_walk.py): market-style stages (structure_stop/ribbon_flip/time_stop) fill at that bar's close minus $0.02 slippage; limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the triggered premium level. Frictionless beyond that (no spread/queue modelled).
- descriptive_shakeout_stat's 'structure_confirmed_by_eod' answers a DIFFERENT question than 'premium_recovered_past_exit' -- a trade can be a genuine early-vs-late-by-minutes call (structure confirms shortly after, as today's live trade did) without the OPTION premium ever actually recovering (theta/decay can dominate even when the underlying keeps moving favorably) -- both reported, never collapsed into one number.

---
_Source: `backtest/tools/catastrophe_stop_shakeout_ab.py`. Full per-trade detail in the companion `.json`._
