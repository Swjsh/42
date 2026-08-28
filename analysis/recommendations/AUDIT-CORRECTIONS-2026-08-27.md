# AUDIT-CORRECTIONS-2026-08-27 — merged-bucket corruption fix + structural guards

**Scope:** analysis-path only. No `params*.json` / `heartbeat*` / `filters.py` / `strategies.py`
/ `fleet_executor.py` / `risk_gate.py` / `exit_manager.py` / any live-order-path file touched.
Fixes LIVE CORRUPTION an adversarial audit found in 4 A/B scorecards + the September-tune
overlap matrix (commit `12f86c11`), formalizes the round-trip BASIS question the repo had 3
unreconciled answers to, and makes the audit's #1 structural recommendation (4 missing guard
fields) load-bearing on every scorecard cell going forward via a new shared helper.

## 1. What was verified (quoted, computed fresh this session)

All four of the audit's claims were reproduced independently before any fix was applied:

1. **Phantom positions.** `premium_cost_cap_1200.json`'s `n_blocked_full_list` contained rows
   with `cost: 8816.0` (risky-3, 2026-08-05, `SPY260805C00776000`) and `cost: 5510.0` (risky-1,
   same date/symbol). Recomputing the OLD (pre-`26e69762`) merged-bucket method directly from
   `automation/state/fills-ledger.jsonl` reproduces **both figures exactly** (`OLD max cost
   engine = 8816.0`), and the corrected `analysis/trades-enriched.jsonl` gives **`max
   cost_dollars engine balanced = 1880.0`** — confirms the true max.
2. **Phantom "winners."** The claimed 5 merge-artifact "winners" (~+$1,670 combined) trace to
   real double-counted rows — e.g. risky-1 2026-08-04 `SPY260804C00769000` "cost 1270 / pnl
   +541" is genuinely two separate legs: entry 11:52:10→11:57:07, cost $605, pnl **-$110**; and
   entry 12:28:10→13:51:07, cost $665, pnl **+$651** (605+665=1270, -110+651=541 — confirms the
   merge, and confirms **neither leg individually crosses the $1,200 cap**, so this row should
   never have been in the blocked list at all).
3. **The basis had 3 unreconciled answers**, all now verified directly against
   `automation/state/fills-ledger.jsonl`:

   | Basis | Method | Engine option round trips, August 2026 | August P&L |
   |---|---|---|---|
   | **REFUTED** merged-bucket | pre-`26e69762` `trades_enriched.py` (one row per (date,arm,symbol), no split) | **147** | **+$1,744** |
   | `flat_to_flat` | `trades_enriched.py` (post-`26e69762`, this repo's canonical behavioral basis) | **210** | **+$1,744** |
   | FIFO | `broker_fills.py:fifo_round_trips` (canonical P&L-accounting basis; feeds `pnl-statement.json` + every journal EOD block) | **293** | **+$1,744** |

   P&L is identical on **all three** bases (fill-additive) — even the refuted basis reproduces
   $1,744, which is exactly why the corruption was invisible to any P&L-only check. WR and
   payoff are NOT basis-invariant: **WR 34.76% (`flat_to_flat`) vs 44.03% (FIFO)**; **payoff
   ~2.04x (`flat_to_flat`) vs ~1.38x (FIFO)** (the task's own framing quoted 2.10x/1.38x —
   corrected to 2.04x/1.38x, measured this session, small enough to be the same finding).
   Profit factor was checked empirically and found basis-invariant for this population (GP
   $16,316.00 / GL -$14,572.00 / PF 1.1197, identical on both bases to the cent) — this is
   **not asserted as a general guarantee** (a trip that splits into mixed-sign FIFO legs could
   in principle move GP/GL between buckets); it held here and is documented as an empirical
   finding, not a proof.
4. **journal/2026-08-12.md's 47 trips** reproduce **exactly** under FIFO on the real ledger
   (`broker_fills.fifo_round_trips`, all attributions, 2026-08-12: n=47).
5. **Cross-arm correlation.** `analysis/journal/calendar-data.json` documents r=0.846 /
   95.7% sign agreement (2026-08-06 analysis). An independent same-session recomputation
   (day-level engine P&L, pairwise Pearson r + sign agreement across the 5 active arms
   safe-2/bold-2/safe-3/risky-1/risky-3, mean of 10 pairwise values) gives **r=0.717, sign
   agreement 85.7%** — lower than the 08-06 figure (recency drift, consistent with the standing
   "recency > aggregate" doctrine), and in the same ballpark as this task's own cited
   independent measurement (r=0.759/83.8%). Both confirm the arms are meaningfully
   non-independent, well below r=1 but well above r=0 — this is why guard (i) below bootstraps
   by DAY, not by trade: resampling whole days preserves whatever the true within-day
   correlation structure is without having to pin down its exact value.

## 2. Root cause

`setup/scripts/trades_enriched.py`'s `build_round_trips` bucketed all fills for a
`(date, arm, symbol)` key into ONE row without checking whether the position returned to flat
and reopened same-day (e.g. `vwap_continuation` firing 3x on one strike). `pnl_dollars` stayed
correct (additive across the bucket) but `cost_dollars`, `hold_min`, `entry_px`, and
context-join fields were silently wrong for any bucket containing more than one real position.
Commit `26e69762` (same evening, LATER than `12f86c11`) fixed this in `trades_enriched.py`
itself, but the 4 scorecards + overlap matrix from `12f86c11` were never regenerated against
the fix — they shipped, and stayed, on the refuted basis. **No generator script for those 5
files was ever committed** (a `C35` violation independent of the data bug — "built + tested"
without a re-runnable artifact means the corruption couldn't even be diffed, only re-derived
from scratch, which is what this pass had to do).

## 3. What changed

### `setup/scripts/trades_enriched.py` — basis + FIFO reconciliation fields
Every row now carries `basis: "flat_to_flat"` plus `fifo_trip_ids` / `fifo_trip_count` /
`fifo_trip_pnl_sum` — computed via a new `_fifo_legs_for_trip()` that FIFO-pairs each trip's
OWN fills (safe to scope per-trip: a flat-to-flat trip returns the position to exactly zero at
its own boundary, so its fills can never FIFO-match a fill from a different trip). `_meta` gains
`fifo_trip_count_total`, `flat_to_flat_pnl_total`, `fifo_pnl_total_via_flat_to_flat_rows` (must
match, and do: **-96.0 vs -96.0** across the whole ledger), and an explicit
`basis_reconciliation_doc` note. Regenerated `analysis/trades-enriched.jsonl` (377 rows, same
count as before the basis fields were added — this was a field-addition, not a
row-count-changing fix; `26e69762` already did the row-count fix).

### `setup/scripts/lib/scorecard_guards.py` (NEW) — the audit's 4 required guard fields
Stdlib-only, deterministic (seeded), $0. Four functions:
- `day_level_bootstrap` — bootstraps by TRADING DAY (never by trade, per the correlation
  finding above), returns pnl CI + `P(pnl<=0)` and PF CI + `P(PF<=1.0)`.
- `ex_best_day` — removes the single best day, reports `auto_fail_sign_flips_ex_best_day`
  (the audit's required field name, verbatim).
- `signal_cluster_n` — collapses near-simultaneous same-symbol entries across arms into one
  cluster. **Window: 60 seconds**, justified from real-tape timestamp gaps verified this
  session: same-signal entries across arms land 1–70s apart (e.g. 2026-08-04 11:51:41 →
  11:52:12 across bold-2/safe-3/risky-1/risky-3, one signal, 4 fills, 31s spread); a genuinely
  separate re-trigger of the same strike lands 4–40+ minutes later in every observed case
  (e.g. 09:46 vs 09:50 vs 09:58 on 2026-08-04's `SPY260804C0076[23]000`). 60s absorbs
  execution-path latency without merging distinct signal instances.
- `benjamini_hochberg` — standard BH step-up, q=0.10, excludes cells with no p-value from the
  correction (never coerces to 0/1).

19 unit tests in `backtest/tests/test_scorecard_guards.py` (deterministic-seed check, PF-
undefined-on-all-wins, classic textbook BH worked example, transitive clustering chain, etc.),
all passing.

### `backtest/tools/sept_tune_audit_correction_2026_08_27.py` (NEW) — the regenerator
The first COMMITTED, re-runnable generator for this scorecard sweep. Reads the corrected
`analysis/trades-enriched.jsonl` (`flat_to_flat` basis — the right unit for these 4
ENTRY-time-decision rules; FIFO's finer split would force awkward multi-leg blocking of a
single entry decision). Rebuilds all 4 rules identically to the original definitions
(premium-cost-cap sweep 800/1200/1600, VWAP-family block + $600-rescale variant, mixed-ribbon
core-only block, 12:00–13:00 ET block), adds the 4 guard fields per cell, runs BH-FDR once
across the whole 6-cell sweep (4 rules + the 800/1600 sweep points), and writes each output
under its ORIGINAL filename with the old (corrupted) content preserved verbatim under a
`superseded_by_audit_2026_08_27` key plus a top-level `basis` field, per the audit's
disclosure requirement.

**Anchor cohort — REDEFINED, disclosed.** The original files' `anchor_cohort_n=33` /
`anchor_winners_n=11` has no recoverable definition anywhere in the repo (no committed script,
no doc — grepped `analysis/deep-research/`, `markdown/`, and every `.py` file for "anchor
cohort"/33/11 in combination; nothing matches). This pass defines it explicitly and documents
the choice in every regenerated file's `anchor_check.anchor_cohort_definition`: **engine trades
using setup `BULLISH_RECLAIM_RIDE_THE_RIBBON`/`BEARISH_REJECTION_RIDE_THE_RIBBON` with
`stop_mode=="structure"`** — the current v15.3 chart-stop-primary production strategy, which
`markdown/planning/FUTURE-IMPROVEMENTS.md`'s own SEPT-TUNE intro names as "the edge...
everything else subtracted." This cohort is larger (n=177, 68 winners) than the unrecoverable
original (n=33, 11 winners) because it is the FULL production-strategy cohort, not whatever
narrower slice the original session chose and never wrote down. **This is the single biggest
source of verdict change below** (see §4) — flagged explicitly rather than presented as if it
reproduces the original.

## 4. Per-rule gate verdict: before vs after

| Rule | OLD n_blocked | OLD verdict | NEW n_blocked | NEW verdict |
|---|---|---|---|---|
| `premium_cost_cap_1200` | 20 (phantom-inflated) | BLOCKED — WF-proxy 0.079 <0.70 | **10** | BLOCKED — OOS_delta<=0; WF-proxy 0.0 <0.70 |
| `vwap_family_demotion` | 17 | BLOCKED — WF-proxy 0.182 <0.70 | **37** | BLOCKED — WF-proxy 0.191 <0.70; removes 3 anchor-cohort winners; ex-best-day sign flip |
| `mixed_ribbon_gate` | 7 | **PASSES all hard gates** (OOS+, WF 3.96, 3/4 weeks, anchor clean) — flagged small-sample only | **7** | **BLOCKED** — removes 2 anchor-cohort winners (under the redefined, broader anchor cohort — see §3); evidence_n=7 (advisory) |
| `lunch_window_gate_1200_1300` | 24 | BLOCKED — OOS negative, removes 2 anchor winners | **44** | BLOCKED — WF-proxy 0.2 <0.70; removes 15 anchor-cohort winners; ex-best-day sign flip |

**Bottom line is unchanged: hold all 4 in shadow, ship none.** The one material verdict
change is `mixed_ribbon_gate`, which previously cleared every hard gate (with an n=7
small-sample caveat) and now fails `anchor_no_regression`. This is disclosed, not
soft-pedaled: it is **substantially a consequence of the anchor-cohort redefinition**
(§3) rather than new information about the rule's blocked-trade set, which is
identical in count (n=7) to before. Anyone revisiting this candidate should re-derive
their own anchor cohort rather than trust either number blindly, given neither the old
nor the new one is a "ground truth" — the old one is simply undocumented.

**New this pass, independent of anchor cohort:** BH-FDR across the 6-cell sweep (4 rules + the
premium-cap 800/1600 sweep points) rejects **zero** cells at q=0.10. The best (smallest)
one-sided bootstrap p-value for "this rule's dollar benefit is real" is
`premium_cost_cap_1200@1200` at p=0.0455 — nominally under 0.05, but needs p<=0.0167 to survive
FDR correction at rank 1 of 6. This is an independent line of evidence (bootstrap +
multiple-comparisons correction) pointing the same direction as the gate ladder: nothing in
this sweep is strong enough to ship yet. Full p-values and BH detail:
`SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json`'s `fdr_across_sweep` block.

`signal_cluster_n` disclosure: every rule's raw `n_blocked` fill count overstates its
independent-evidence count once the 5-arm shared-signal correlation is accounted for — e.g.
`lunch_window_gate_1200_1300`'s 44 raw blocked fills collapse to **25** independent signal
clusters (60s same-symbol window), `vwap_family_demotion`'s 37 to **30**,
`premium_cost_cap_1200`'s 10 to **9**, `mixed_ribbon_gate`'s 7 to **6**.

## 5. Files changed

- `setup/scripts/trades_enriched.py` — basis + FIFO reconciliation fields (edit).
- `analysis/trades-enriched.jsonl` — regenerated (basis fields added, same 377-row shape).
- `backtest/tests/test_trades_enriched.py` — 4 new tests pinning the basis reconciliation.
- `setup/scripts/lib/scorecard_guards.py` — NEW shared guard helper.
- `backtest/tests/test_scorecard_guards.py` — NEW, 19 unit tests.
- `backtest/tools/sept_tune_audit_correction_2026_08_27.py` — NEW, the committed regenerator.
- `analysis/recommendations/premium_cost_cap_1200.json`,
  `vwap_family_demotion.json`, `mixed_ribbon_gate.json`,
  `lunch_window_gate_1200_1300.json`,
  `SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json` — regenerated, filenames unchanged, old
  (corrupted) values preserved under `superseded_by_audit_2026_08_27` in each file.
- `markdown/planning/FUTURE-IMPROVEMENTS.md` — pointer line appended under the existing
  "NEW 2026-08-27 -- SEPTEMBER TUNE LIST" section (append-only, per OP-22 fold rule).
- This file.

## 6. C7 verification (quoted, run fresh this session)

```
[trades_enriched] wrote 377 rows to analysis\trades-enriched.jsonl
[verify] 2026-08-27 engine round trips: n=12 (want 12) pnl=$1897.00 (want +$1897 +/-$5) -> PASS
[verify] August 2026 engine total: n=210 pnl=$1744.00 (want +$1744 +/-$10) -> PASS
```

```
[audit-correction] population (flat_to_flat, engine, 2026-07-01..2026-08-27): n=345 pnl=$377.00
[audit-correction] max cost_dollars in population: $1880.00 (must be <= $1,880)
[audit-correction] BH-FDR q=0.1 across m=6 cells: rejected=[]
```

```
max cost found across all 4 NEW scorecards (excluding superseded blocks): 1880.0
PASS: no scorecard cell contains a position cost > $1,880
```

`pytest backtest/tests/test_trades_enriched.py backtest/tests/test_scorecard_guards.py -q`:
**31 passed**. Full-tree `pytest --collect-only` (10,241 tests) confirms no collection/import
errors introduced anywhere in the tree. `backtest/tests/test_graduated_guards.py` (repo-wide
pattern-scan + backtest-simulation guard suite, 5,080 lines, incl. the L160 anchor-formula
check this module's `anchor_check` logic does NOT reuse the broken form of) run separately in
the background — **129 passed, 1 skipped in 1168.13s (19m28s), exit code 0**, no failures.

## 7. Commit

`ee8adbe0` — pathspec-commit of exactly the 13 files listed in §5 (verified via `git status
--porcelain` before commit: no other paths staged). Pre-commit's curated safety gate (6 suites,
59 tests) ran automatically and passed.
