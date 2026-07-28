# SCORE LADDER full-history replay -- 2025-01-02 .. 2026-07-27

Generated 2026-07-27T21:05:01.875347. Runner: `backtest/tools/ladder_fullhist_replay.py`. Runtime: 91.1s total (68.6s entry/scoring layer).

## Verdict first

| Lane | N trades | Total P&L | WR | Avg/trade | Max DD | Day-majority | Survives drop-best | Held-out (last 25%) | Synthetic excluded |
|---|---|---|---|---|---|---|---|---|---|
| **BASELINE (binary engine)** | 191 | +$5306.95 | 0.2984 | +$27.79 | -$2233.40 | 49/142 (False) | +$4447.00 (True) | 58tr +$1548.40 | -- |
| **Ladder floor=7** | 1538 | -$31015.05 | 0.2991 | -$20.17 | -$32474.40 | 123/353 (False) | -$33073.05 (False) | 465tr -$7274.40 | 544/4388 (26.1%) |
| **Ladder floor=8** | 725 | -$16641.90 | 0.2938 | -$22.95 | -$18450.00 | 94/243 (False) | -$17690.90 (False) | 229tr -$3348.20 | 351/2308 (32.6%) |
| **Ladder floor=9** | 332 | -$10903.50 | 0.238 | -$32.84 | -$14410.05 | 51/158 (False) | -$11894.50 (False) | 103tr +$2866.00 | 140/763 (29.7%) |

## Calibration check -- 2026-07-27 09:40 (the incident deb781ea's own commit cites)

- Reproduced: bear_score=8, blockers=[5, 9], triggers=['level_rejection'], rejection_level=745.0, bull_passed=False
- Pinned live-incident ground truth: bear_score=9, blockers=[5], trigger=level_rejection, rejection_level=744.9
- **Exact match: False. Roughly reproduces: True.**
- Off-by-one from the pinned ground truth (bear_score/blockers/rejection_level all shift by a small amount) -- the SAME known feed-provenance gap already root-caused same-day in analysis/arm-ladder/ARM-LADDER-V1-2026-07-27.md: the cached 09:40 bar in backtest/data/spy_5m_2026-05-19_2026-07-27.csv is not byte-identical to the real IEX bar the live engine read (a few cents on open/high/low), which shifts filter 5's confluence match and filter 9's volume-baseline check. Not re-investigated here -- citing the existing, already-verified finding rather than re-deriving it.
- Would qualify at floor 7: True | floor 8: True | floor 9: False
  - Lane floor=7: candidate excluded (no_opra_cache)
  - Lane floor=8: candidate excluded (no_opra_cache)
  - Lane floor=9: candidate excluded (no_opra_cache)

## Disclosures

- replay-vs-live divergence is KNOWN (engine_fullhist_replay.py's own fidelity check: the entry layer's single-isolated-bar reconstruction does not always land on the identical bar as a live fill on days with intraday state, e.g. 2026-07-17 anchors 2/4 -- see that tool's ANCHOR_DAY sanity check). This ladder replay inherits the same entry-layer scope/limitation for its scoring inputs.
- Held-out split: last ~25% of the window (cutoff 2026-03-06), touched once (reported, not used to tune floors/exit shape).
- Synthetic-premium share: BS-synthetic entries are flagged per-trade (`is_synthetic`/`synthetic_entry_premium` in the JSON) and counted separately per lane (`n_excluded_synthetic_priced` / `pct_synthetic_of_would_be_entries`) -- they are NEVER blended into the P&L/WR/expectancy numbers above (real OPRA fills only; see module docstring for why a synthetic exit walk was not attempted).
- Baseline data quality: 18 entries excluded (no OPRA cache), 0 excluded (no SPY day).
- Entry price convention: NEXT option bar's OPEN after the trigger bar (entry+1, per markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md) -- deliberately matches walk_exit_manager's own point-sample-at-open exit convention, NOT simulator_real.py's VWAP-based convention for the binary engine's own real entries.
- One-position-at-a-time (NOT_FLAT) discipline is per-lane, independent across floors 7/8/9 -- each lane can be in a DIFFERENT position (or flat) at the same wall-clock time.

## Honest read

Across 390 RTH days (2025-01-02..2026-07-27), the binary engine's own entries produced +$5306.95 on 191 trades (WR 0.2984). The 3 score-ladder lanes, walked one-position-at-a-time on min-size (3 contracts, ATM strike, the SAME structure-stop RIBBON_RIDE exit shape) against every bar the binary engine scored-but-refused, produced floor=7 -$31015.05 (n=1538, WR=0.2991), floor=8 -$16641.90 (n=725, WR=0.2938), floor=9 -$10903.50 (n=332, WR=0.238). The best-performing lane by total P&L is floor=9 (-$10903.50, day-majority=False, survives-drop-best=False, held-out-last-25%=+$2866.00). This is a HYPOTHESIS-UNDER-TEST replay of a lane that ships on ONE live account (risky-3, floor=7) -- the numbers above are the honest full-history evidence for or against widening it, not a claim that any number here already matches what risky-3's own forward paper ledger will show (see the known-divergence disclosure).

---
_Raw JSON with full per-trade/per-excluded-candidate detail: `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json`._
