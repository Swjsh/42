# FDR-16-OPRA-CONFIRM — real-fills confirmation of the FDR screen's top-2 non-redundant survivors

Generated: 2026-07-11T18:41:16.332574. Source: `backtest/tools/fdr16_opra_confirm.py`. Ticket: `FDR-16-OPRA-CONFIRM` (queue.md, queued 2026-07-02).

## VERDICT TABLE

| group | n (true) | signal exp/tr | null mean/max | opp-dir exp/tr | verdict |
|---|---|---|---|---|:--:|
| groupA_level_rejection_long_vixlo | 619 | $39.12 | $9.87/$33.36 | $-22.94 | **KILL** |
| groupB_trendline_rejection_long_vixhi | 160 | $-20.32 | $-11.11/$80.02 | $-6.12 | **KILL** |

## N-HONESTY (found while building this confirmation, applies to the ORIGINAL FDR screen)

- **groupA_level_rejection_long_vixlo**: FDR screen reported n=1318 (p=9.998e-08) but only **840 are TRUE distinct bars** (478 bars double-logged, 1.569x inflation). Recomputed at the true n: t=4.019, p=2.920e-05
- **groupB_trendline_rejection_long_vixhi**: FDR screen reported n=338 (p=7.718e-05) but only **180 are TRUE distinct bars** (158 bars double-logged, 1.878x inflation). Recomputed at the true n: t=2.675, p=3.740e-03

## Per-group detail

### `groupA_level_rejection_long_vixlo` — level_rejection / long / vix_lo

- **Verdict: KILL** — fails standard null gate (beats_null_max=True, drop_top5_beats_null_mean=False) -- exit-structure artifact, not signal alpha (C3/L58)
- Signal (real OPRA fills, qty=10, production-default exit shape): n=619 (of 664 signals, 45 no cached data), total=$24214.4, expectancy=$39.12/tr, WR=0.252
  - top-3-day concentration: $13617.8 of $24214.4 total (0.562)
  - drop-top5 expectancy: $5.72/tr
  - IS(2025) n=418 exp=$15.07 | OOS(2026) n=201 exp=$89.14
- Opposite-direction null (same bars, side flipped): n=607, expectancy=$-22.94/tr, WR=0.217
- Random-entry null (20 seeds, same vix-regime+time pool, n_eligible=9367): mean=$9.87/tr, max=$33.36/tr
  - null_gate: beats_null_max=True, drop_top5_beats_null_mean=False, edge_over_null=$29.25 -> null_pass=False

### `groupB_trendline_rejection_long_vixhi` — trendline_rejection / long / vix_hi

- **Verdict: KILL** — real-fills expectancy -20.32 <= 0
- Signal (real OPRA fills, qty=10, production-default exit shape): n=160 (of 190 signals, 30 no cached data), total=$-3252.0, expectancy=$-20.32/tr, WR=0.225
  - top-3-day concentration: $4865.0 of $-3252.0 total (-1.496)
  - drop-top5 expectancy: $-72.23/tr
  - IS(2025) n=30 exp=$-98.91 | OOS(2026) n=130 exp=$-2.19
- Opposite-direction null (same bars, side flipped): n=150, expectancy=$-6.12/tr, WR=0.24
- Random-entry null (20 seeds, same vix-regime+time pool, n_eligible=4662): mean=$-11.11/tr, max=$80.02/tr
  - null_gate: beats_null_max=False, drop_top5_beats_null_mean=False, edge_over_null=$-9.21 -> null_pass=False

## Disclosures

- n-honesty: the FDR screen's reported n is inflated (~1.57x-1.88x on these two groups) by exact-duplicate decision-log rows per bar in shadow-ledger.jsonl (see n_honesty per group) -- this script trades each TRUE distinct bar exactly once.
- qty=10 fixed; absolute $/expectancy ignore the kill switch + per-trade cap -- relative-to-null and the opposite-direction comparison are the trustworthy signals (same caveat as every T4/T5 pass).
- Production-DEFAULT exit shape (simulate_trade_real's own defaults: premium_stop_pct=-0.08 v14-ratified, strike_offset=-2 ITM-2 v15-ratified) -- no custom exit shape was specified by the ticket, so this answers 'what would our current engine's default management have done.'
- ribbon_df=None for all replays (signal, opposite-direction, both nulls) -- apples-to-apples; ribbon-flip/level-memory overlays are NOT modeled (this is a brand-new setup family with no production ribbon wiring yet).
- Group A (level_rejection) rejection_level is the REAL level the live engine detected at that bar. Group B (trendline_rejection) rejection_level=None -- matches the live engine's OWN decision record (trendline-only triggers do not populate the shared rejection_level slot in filters.py), NOT an invented shortcut.
- Frictionless fills at trigger levels; entry fills next-bar VWAP; direction proxy -> real option P&L conversion carries the same C3 risk that killed NLWB.
- Random-entry null and opposite-direction null are DISTINCT checks: random-entry isolates signal-timing value from exit-structure (standard repo gate, null_baseline.py); opposite-direction isolates whether the edge is directional or a broad-drift artifact.
- SPEC-VS-REALITY: this script regenerates decisions with CURRENT production params (automation/state/params.json, mtime 2026-07-09T22:57:47.684170), not the params in effect when the original shadow-ledger.jsonl was built (mtime 2026-06-29T17:37:10.880840, 10.2 days earlier). That param drift is the most likely reason the regenerated true-distinct-bar counts (see per-group n_honesty) don't exactly match a fresh re-derivation from the frozen ledger file -- this is arguably the MORE relevant test (does the edge exist under what we'd actually deploy today, not a 12-day-stale detector), but it is a real methodological difference from 'exactly reproduce the screened population,' disclosed rather than buried.

---
_KILL is a fully valid outcome per the ticket's own framing: 16 FDR survivors out of 162 comparisons can still be multiplicity noise once real premium decay/spread/strike selection is modeled (C3) — the same failure mode that killed NLWB (analysis/recommendations/nlwb_full_real_fills.json)._
