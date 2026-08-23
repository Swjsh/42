# TP1-R50 Extended Re-adjudication -- 2026-08-23

**VERDICT: R_tp100_f50 STILL FAILS G4_subwindow_stable on the extended population -- DO_NOT_ARM stands. Prereg stays FROZEN.**

PREMATURE_CLOCK label: NO -- clock triggered, see Part 1

## Part 1 -- forward-clock trigger

- risky-1 exit_patch (verified live): `{'tp1_premium_pct': 0.5, 'stop_mode': 'structure'}`
- journal/trades.csv (primary, real fills): **n=35** position-level ribbon fills post-2026-08-03 (51 leg-rows)
- decisions.jsonl cross-check: n=35 placed=true ENTER rows (34 matched within 15s)
- **CLOCK MET (n-floor)** (floor=30, calendar deadline 2026-09-05 not yet passed)

## Part 2 -- extended population A gate re-run

- cache last date: 2026-08-21; extension window 2026-07-23..2026-08-21
- extension: 22 new ribbon_ride entries (0 excluded no-OPRA, 0 excluded no-SPY-day)
- combined popA n = 213 (191 original frozen + 22 new)
- **VOID check: PASS, 0 mismatches**

### G4 sub-windows (extended)

| Window | Delta | N changed | Qualifies (>=5)? |
|---|---:|---:|:---:|
| 2025H1 | $+228.95 | 4 | no |
| 2025H2 | $+333.20 | 13 | yes |
| 2026Q1 | $+253.20 | 4 | no |
| 2026Q2p_ext | $+151.95 | 14 | yes |

### Full 8-gate table (R_tp100_f50, extended)

| Gate | Result | Scope |
|---|:---:|---|
| G1_popA_aggregate | PASS | popA (RE-RUN, extended) |
| G2_ex_best_trade | PASS | popA (RE-RUN, extended) |
| G3_runner_anchor | PASS | popA (RE-RUN, extended) |
| G4_subwindow_stable | FAIL | popA (RE-RUN, extended) |
| G5_drop_best_day | PASS | popA (RE-RUN, extended) |
| G6_week_tuesday_HARD | PASS | week B (CARRIED FORWARD, not re-run) |
| G7_week_total | PASS | week B (CARRIED FORWARD, not re-run) |
| G8_bh_fdr | PASS | 28-cell family (CARRIED FORWARD, not re-run) |

**FAILS: G4_subwindow_stable**

G4 structural finding: G4 requires >=3 of the sub-windows (among those with >=5 changed trades) to be delta>=-$0.005, AND at least 2 windows must qualify (>=5 changed trades) at all. 2025H1 and 2026Q1 are FIXED CALENDAR-PAST windows sitting at n_changed=4 each (both original 2026-08-06 run and this extended run) -- a forward extension of popA's END date can only ever add trades to the newest (4th) window; it cannot retroactively add trades to a window that is entirely in the past. Only 2 of the 4 windows (2025H2 n=13, 2026Q2p_ext n=14) can ever qualify under this population-extension approach, so the >=3-qualifying-and-positive requirement is STRUCTURALLY UNREACHABLE via this lever alone -- extending popA's window further forward (e.g. through a later cache date) would grow the 4th window further but still cannot create a 3rd qualifying window. G4 did not fail this run for the same reason it failed originally (power/dispersion, all windows positive) -- it fails now for a DIFFERENT, sharper reason: the gate's own qualification structure caps out at 2 qualifying windows for this population, permanently, under any forward-only extension.

## Part 3 -- live-arm corroboration (proxy)

risky-1 varies TP1 LEVEL (+50% vs siblings' +100%) at a FIXED qty_fraction (registry 0.667, unchanged by risky-1's exit_patch). Cell R_tp100_f50 varies QTY FRACTION (0.5 vs 0.667) at a FIXED +100% TP1. Different knobs; this section is a PROXY on the shared 'early extraction damages runners' risk only, never direct evidence for/against R_tp100_f50's own axis.

- 25 risky-1 ribbon signals post-2026-08-03 shared with >=1 sibling arm
- coarse (total position $) delta risky-1 minus siblings: $+1,050.00
- runner-leg proxy delta risky-1 minus siblings: $+513.00 (n=6 multi-leg paired signals -- SMALL SAMPLE, read with caution)
- **CONTRADICTS the risk on this small live sample (risky-1 ahead on both cuts)**

---
_Source: backtest/tools/tp1_r50_readjudication_2026_08_23.py + backtest/tools/tp1_r50_live_arm_2026_08_23.py + backtest/tools/tp1_r50_assemble_2026_08_23.py. Full JSON: analysis/recommendations/tp1-r50-readjudication-2026-08-23.json._
