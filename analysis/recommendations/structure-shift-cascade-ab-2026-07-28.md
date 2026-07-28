# Structure-shift CASCADE A/B (pre-reg #2) -- 2026-07-28

**VERDICT: DO_NOT_ARM** -- G1=False G2=True G3=False G4=False G5=False | evidence_floor(n_changed>=10)=True (n_changed=20)

Tool: `backtest/tools/structure_shift_cascade_ab.py`. Pre-reg: `analysis/recommendations/prereg-structure-shift-cascade-2026-07-28.json` (commit 58bb61fa). Wiring under test: commit 459342c8. Runtime: 80.5s total (control entry 78.3s, control exit 1.8s, candidate scoring 0.2s).

## Plumbing route

run_backtest does not forward bear_kwargs/bull_kwargs (verified: no such kwarg in its signature, hardcoded evaluate_bearish_setup/evaluate_bullish_setup calls). Route taken: engine_cli.decide_payload per flagged candidate bar, gate_params.structure_shift_confirmation_enabled=True, bar_ctx serialized from the ORIGINAL orchestrator BarContext captured via a pass-through monkeypatch (byte-identical inputs, not a heartbeat_core-style rebuild), bear_kwargs/bull_kwargs the SAME constant kwargs orchestrator computed for this run. Bull side proven a no-op for entries (passed independent of the htf demerit) -- only bear candidates (blockers==[5]) are re-scored.

## Baseline anchor

CONTROL runs the EXTENDED window 2025-01-02..2026-07-27 (engine_fullhist_replay.py's own window ends 2026-07-22, before the G5 anchor -- extended here, same precedent as ladder_fullhist_replay.py, so the 07-27 anchor is reachable). The <=2026-07-22 PREFIX of CONTROL's trades (a strict prefix -- orchestrator is causal, nothing after 07-22 can change an earlier trade) reproduced n=190 total=+$5064.75 vs stored n=190 total=+$5064.75 -- **PASS**. Full extended-window CONTROL: n=191 total=+$5005.95.

## Gate table

| Gate | Detail | Pass |
|---|---|---|
| G1 positive aggregate | delta -$46.00 (+$5005.95 -> +$4959.95) | False |
| G2 day-majority | 10 improved / 6 worsened of 16 changed days | True |
| G3 survives drop-best | -$625.00 after dropping the best single changed trade (+$579.00) | False |
| G4 preemption (no negative day) | 7 baseline trade(s) preempted | False |
| G5 07-27 09:40 bear anchor added | 0 matching trade(s) | False |
| Evidence floor (n_changed>=10) | n_changed=20 | True |

### G5 root-cause (FAIL)

Every bear-side evaluation on 2026-07-27 in THIS run (not just blockers==[5] candidates), for root-cause visibility on why the anchor was/wasn't captured. Cross-reference against ladder_fullhist_replay.py's own 09:40 calibration check (analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json#calibration_2026_07_27_0940): that tool's own independently-derived ground truth for this exact bar is bar_idx=29113, bear_score=8, blockers=[5, 9], rejection_level=745.0 -- i.e. even in that tool's run the 09:40 bar has TWO blockers (5 AND 9, the volume-baseline filter), not blockers==[5] alone, and rejection_level is already off by $0.10 from the pinned live-incident level (744.9). That tool's own note attributes this to a pre-existing, already-root-caused feed-provenance gap: 'the cached 09:40 bar in backtest/data/spy_5m_2026-05-19_2026-07-27.csv is not byte-identical to the real IEX bar the live engine read'. Filter 9 (volume) is NOT touched by structure_shift_confirmation (only filter 5 bear / the HTF-demerit bull), so even with perfect data fidelity this specific bar could not flip to ENTER_BEAR via the shift mechanism alone -- G5's FAIL here traces to pre-existing cached-data limitations at the historical window's tail edge, not a defect in this A/B's methodology (the <=2026-07-22 baseline anchor reproduces the stored scorecard EXACTLY, n=190 $5,064.75, proving the methodology is faithful over the 18-month core window).

Full bear-side scan of 2026-07-27 in this run (every evaluated bar, not just blockers==[5] candidates):

| Bar idx | Time ET | Bear score | Blockers | Triggers | Level | Ribbon |
|---|---|---|---|---|---|---|
| 29112 | 09:35 | 7 | [5, 8, 9] | ['level_rejection'] | 745.45 | MIXED |
| 29113 | 09:40 | 8 | [5, 9] | ['level_rejection'] | 745.0 | BULL |
| 29114 | 09:45 | 6 | [5, 7, 8, 9] | ['level_rejection'] | 744.1 | BULL |
| 29115 | 09:50 | 7 | [5, 7, 9] | ['level_rejection'] | 744.1 | BULL |
| 29116 | 09:55 | 7 | [5, 9, 10] | [] | None | BULL |
| 29117 | 10:00 | 5 | [5, 7, 8, 9, 10] | [] | None | BULL |
| 29118 | 10:05 | 5 | [5, 7, 8, 9, 10] | [] | None | BULL |
| 29119 | 10:10 | 7 | [5, 9, 10] | [] | None | BULL |
| 29120 | 10:15 | 6 | [5, 8, 9, 10] | [] | None | BULL |
| 29121 | 10:20 | 7 | [5, 9, 10] | [] | None | BULL |
| 29122 | 10:25 | 9 | [5] | ['level_rejection', 'confluence'] | 739.3487259899708 | BULL |
| 29123 | 10:30 | 7 | [5, 6, 10] | [] | None | MIXED |
| 29124 | 10:35 | 7 | [6, 9, 10] | ['ribbon_flip'] | None | BEAR |
| 29125 | 10:40 | 9 | [9] | ['level_rejection', 'ribbon_flip', 'confluence'] | 737.29 | BEAR |
| 29126 | 10:45 | 7 | [8, 9, 10] | ['ribbon_flip'] | None | BEAR |
| 29127 | 10:50 | 8 | [8, 9] | ['level_rejection', 'confluence'] | 738.7 | BEAR |
| 29128 | 10:55 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29129 | 11:00 | 8 | [9, 10] | [] | None | BEAR |
| 29130 | 11:05 | 9 | [8] | ['level_rejection', 'confluence'] | 739.3487259899708 | BEAR |
| 29131 | 11:10 | 8 | [8, 9] | ['level_rejection'] | 739.35 | BEAR |
| 29132 | 11:15 | 9 | [9] | ['level_rejection', 'confluence'] | 739.3487259899708 | BEAR |
| 29133 | 11:20 | 9 | [9] | ['level_rejection', 'confluence'] | 739.2549751317043 | BEAR |
| 29134 | 11:25 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29135 | 11:30 | 7 | [7, 9, 10] | [] | None | BEAR |
| 29136 | 11:35 | 9 | [9] | ['level_rejection', 'confluence'] | 737.29 | BEAR |
| 29137 | 11:40 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29138 | 11:45 | 9 | [9] | ['level_rejection', 'confluence'] | 737.29 | BEAR |
| 29139 | 11:50 | 8 | [8, 9] | ['level_rejection', 'confluence'] | 737.29 | BEAR |
| 29140 | 11:55 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29141 | 12:00 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29142 | 12:05 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29143 | 12:10 | 9 | [] | ['trendline_rejection'] | None | BEAR |
| 29147 | 12:30 | 8 | [8, 9] | ['level_rejection', 'confluence'] | 739.2549751317043 | BEAR |
| 29148 | 12:35 | 8 | [8, 9] | ['level_rejection', 'confluence'] | 739.3487259899708 | BEAR |
| 29149 | 12:40 | 9 | [9] | ['level_rejection', 'confluence', 'trendline_rejection'] | 739.0304665290166 | BEAR |
| 29150 | 12:45 | 8 | [8, 9] | ['level_rejection', 'confluence', 'trendline_rejection'] | 738.7 | BEAR |
| 29151 | 12:50 | 10 | [] | ['level_rejection', 'confluence', 'trendline_rejection'] | 737.29 | BEAR |
| 29160 | 13:35 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29161 | 13:40 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29162 | 13:45 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29163 | 13:50 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29164 | 13:55 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29165 | 14:00 | 8 | [8, 10] | [] | None | BEAR |
| 29166 | 14:05 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29167 | 14:10 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29168 | 14:15 | 10 | [] | ['level_rejection', 'confluence'] | 737.29 | BEAR |
| 29169 | 14:20 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29170 | 14:25 | 7 | [8, 9, 10] | [] | None | BEAR |
| 29171 | 14:30 | 10 | [] | ['level_rejection', 'confluence'] | 737.29 | BEAR |
| 29172 | 14:35 | 9 | [10] | [] | None | BEAR |
| 29173 | 14:40 | 6 | [7, 8, 9, 10] | [] | None | BEAR |
| 29174 | 14:45 | 8 | [7, 8] | ['level_rejection'] | 737.29 | BEAR |
| 29175 | 14:50 | 5 | [5, 7, 8, 9, 10] | [] | None | MIXED |
| 29176 | 14:55 | 5 | [5, 6, 7, 8, 9] | ['level_rejection', 'confluence'] | 739.1687117289233 | MIXED |
| 29177 | 15:00 | 7 | [1, 5, 6] | ['level_rejection', 'confluence'] | 739.1687117289233 | MIXED |
| 29178 | 15:05 | 4 | [1, 5, 6, 7, 8, 9] | ['level_rejection', 'confluence'] | 739.3487259899708 | MIXED |
| 29179 | 15:10 | 6 | [1, 5, 6, 7] | ['level_rejection', 'confluence'] | 739.3487259899708 | MIXED |
| 29180 | 15:15 | 5 | [1, 5, 8, 9, 10] | [] | None | BULL |
| 29181 | 15:20 | 4 | [1, 5, 7, 8, 9, 10] | [] | None | BULL |
| 29182 | 15:25 | 5 | [1, 5, 8, 9, 10] | [] | None | BULL |
| 29183 | 15:30 | 6 | [1, 5, 8, 10] | [] | None | BULL |
| 29184 | 15:35 | 8 | [1, 5] | ['level_rejection', 'confluence'] | 739.3487259899708 | BULL |

## Headline

- CONTROL total: +$5005.95 (191 trades)
- TREATMENT total: +$4959.95 (197 trades = 184 baseline + 13 shift-added)
- Delta: -$46.00
- Candidates (bear blockers==[5] only): 66
- Flag-off fidelity check (decide_payload reproduces CONTROL's own bear_score/blockers): 66/66 (100.0%)
- Flip to ENTER_BEAR under the flag (scoring + all 15 gates): 19
- Resolved via real OPRA fills: 16
- Excluded (no OPRA cache / min-premium gate): 3
- Preempted baseline trades: 7
- Preempted shift signals (occupied by an earlier-admitted event): 3

## Changed-trade table

| Change | Date | Entry ET | Side | Strike | Qty | Tier | Level | Entry $ | Exit reason | P&L |
|---|---|---|---|---|---|---|---|---|---|---|
| ADDED | 2025-01-14 | 12:05 | P | 581 | 3 | ELITE | 581.2100147980719 | $1.87 | structure_stop @ 581.2100147980719 | -$81.00 |
| ADDED | 2025-06-02 | 12:05 | P | 589 | 5 | ELITE | 589.9 | $0.91 | ribbon_flip_back | -$65.00 |
| ADDED | 2025-08-05 | 10:05 | P | 631 | 3 | ELITE | 631.79 | $1.34 | ribbon_flip_back | +$39.00 |
| PREEMPTED | 2025-08-19 | 13:10 | P | - | 6 | TRENDLINE | None | $0.87 | premium_stop @ 0.7 | -$104.40 |
| PREEMPTED | 2025-09-17 | 13:20 | P | - | 3 | TRENDLINE | None | $2.57 | premium_stop @ 2.06 | -$154.20 |
| ADDED | 2026-04-10 | 10:05 | P | 681 | 3 | ELITE | 680.7 | $1.40 | ribbon_flip_back | -$105.00 |
| PREEMPTED | 2026-04-21 | 13:15 | P | - | 4 | TRENDLINE | None | $1.27 | premium_stop @ 1.02 | -$101.60 |
| ADDED | 2026-05-07 | 12:05 | P | 733 | 5 | ELITE | 733.83 | $1.00 | runner_stop @ 2.19 | +$538.60 |
| PREEMPTED | 2026-05-07 | 12:50 | P | - | 3 | TRENDLINE | None | $1.41 | runner_stop @ 2.41 | +$382.40 |
| ADDED | 2026-05-13 | 09:40 | P | 737 | 3 | ELITE | 737.6190413705132 | $1.57 | ribbon_flip_back | +$84.00 |
| PREEMPTED | 2026-05-18 | 14:05 | P | - | 5 | SUPER | 737.0 | $1.03 | runner_stop @ 2.06 | +$514.40 |
| ADDED | 2026-05-20 | 12:30 | P | 739 | 3 | ELITE | 739.0800170898438 | $1.75 | ribbon_flip_back | +$18.00 |
| PREEMPTED | 2026-06-08 | 14:40 | P | - | 5 | SUPER | 742.0841623480467 | $0.90 | runner_stop @ 2.21 | +$532.00 |
| ADDED | 2026-06-09 | 10:15 | P | 742 | 3 | ELITE | 743.6300048828125 | $2.18 | ribbon_flip_back | -$57.00 |
| ADDED | 2026-06-12 | 11:40 | P | 742 | 3 | ELITE | 743.3599853515625 | $2.33 | ribbon_flip_back | +$480.00 |
| ADDED | 2026-06-25 | 09:50 | P | 733 | 3 | ELITE | 734.37430364919 | $2.71 | structure_stop @ 734.37430364919 | -$252.00 |
| PREEMPTED | 2026-06-25 | 10:00 | P | - | 3 | SUPER | 730.8400268554688 | $2.80 | structure_stop @ 730.8400268554688 | -$579.00 |
| ADDED | 2026-06-25 | 11:15 | P | 733 | 3 | ELITE | 734.37430364919 | $2.18 | ribbon_flip_back | -$234.00 |
| ADDED | 2026-07-20 | 09:55 | P | 746 | 3 | ELITE | 747.75 | $1.33 | ribbon_flip_back | +$60.00 |
| ADDED | 2026-07-20 | 12:30 | P | 746 | 6 | ELITE | 746.8 | $0.76 | ribbon_flip_back | +$18.00 |

## G4 preemption analysis -- every baseline winner preempted by an earlier shift-entry

| Date | Treatment day total | Day pass (>=0) |
|---|---|---|
| 2025-08-19 | +$271.20 | True |
| 2025-09-17 | -$144.00 | False |
| 2026-04-21 | +$384.75 | True |
| 2026-05-07 | +$346.00 | True |
| 2026-05-18 | +$950.70 | True |
| 2026-06-08 | +$439.90 | True |
| 2026-06-25 | -$732.00 | False |

## Disclosures

- SKIP_QUALITY_LOCK escalation lock NOT modeled for new shift-added candidates (scope gap, disclosed in the module docstring -- decide_payload's own documented boundary; reported added-trade counts are a modest upper bound).
- TRENDLINE_LEG2 sizing (prior_stopped + 45min-gap escalation) not modeled; base TRENDLINE qty=3 used for any TRENDLINE-tier admitted trade.
- Synthetic-premium share: 3 candidates excluded (no OPRA cache or below min-premium gate) out of 19 that flipped to ENTER_BEAR -- flagged per-trade in the JSON (`excluded_synthetic`), NEVER blended into the P&L above (real OPRA fills only, same honest-design precedent as ladder_fullhist_replay.py).
- Bull side: the htf-disagreement demerit only ever changes `bull_score`, never `blockers`/`passed` (filters.py `evaluate_bullish_setup`: `passed=(len(blockers)==0)` is computed before the demerit block runs) -- PROVEN a no-op for entry decisions, confirmed by `test_structure_shift_wiring.py::test_htf_bear_demerit_waived_by_shift_confirmation`. Zero bull candidates were scored; this replay is bear-only by construction, matching the pre-reg's own G5 scoping (bull anchor is signal-only).

---
_Raw JSON with full per-trade/per-candidate detail: `analysis/recommendations/structure-shift-cascade-ab-2026-07-28.json`._
