# VWAP_TREND_PULLBACK (H4) — honest real-fills study on the LIVE (chart-stop-only) exit config

_Run 2026-07-23 • pre-registered spec `analysis/recommendations/vwap-trend-pullback-study-spec.json` (frozen 2026-07-10) • real OPRA fills • byte-for-byte detector reuse • $0, pure-Python._

## VERDICT: **KEEP-DORMANT (confirmed reskin of #1 vwap_continuation, gate_11 HARD BLOCK — regardless of gates 1-10)**

Data through 2026-07-22 (387 trading days). Headline tier: ATM, PRIMARY exit config (chart-stop-only, premium_stop_pct=-0.99).

## Gate table

| gate | result |
|---|---|
| gate_2_oos_sign_stable | PASS |
| gate_3_walk_forward_ge_0.70 | FAIL |
| gate_4_sub_window_stable | FAIL |
| gate_5_beats_random_null | PASS |
| gate_6_drop_top3_and_top5_positive | FAIL |
| gate_7_dsr_not_fail | PASS |
| gate_8_causality | PASS |
| gate_11_independence_hard_gate | FAIL |

**gate_11 (HARD, BLOCKING) verdict: CONFIRMED_RESKIN_KEEP_DORMANT** — same-side day-overlap vs #1 vwap_continuation = 1.0 (reskin threshold >= 0.8).

## Headline metrics (PRIMARY, chart-stop-only, ATM)

- n=100, WR=68.0%, exp/tr=$-1.09, OOS exp/tr=$-20.98, WF median=-0.857, sub-window n_hurt=3, DSR=PASS

## gate_10 entry-time distribution

- pct_signals_after_1030 = 0.202 (FALSIFIES the 'fills the afternoon coverage hole' framing per the spec's own hard threshold of 0.30).
- after-10:30-only subset (n=21): exp/tr=$-16.9, OOS stable=False, clears_own_bar=False

## Honest caveats

- Proxy strikes (nearest-cached, L58) — directionally valid, $ modestly off.
- SPY-direction != option edge (C3/L58).
- gate_11 is HARD/BLOCKING per the pre-registered spec: even if gates 1-10 all pass, a confirmed reskin (same_side_overlap >= 0.80 vs #1 AND no independently clearing after-10:30 subset) forces KEEP-DORMANT, full stop.
- This study does NOT wire the detector regardless of verdict (explicit_non_goals in the frozen spec) — a passing scorecard authorizes a NEW proposal doc, not a silent flag flip. J holds REVOKE per Rule 9/OP-25.
