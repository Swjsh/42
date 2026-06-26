# DTE-LIBRARY-SURVEY — does the dead 0DTE directional library reopen at 1-2DTE? (Angle B)

_Run 2026-06-21 • window 2025-01-02..2026-06-16 • SUNDAY/markets-closed • $0 compute • byte-for-byte detectors, no edits to detectors/params/risk_gate/orchestrator/heartbeat._

## VERDICT: **PARTIAL_RESURRECTION**

- Dead families tested: momentum_morning, orb_continuation, power_hour, vwap_pullback (+ vwap_continuation as live control)
- RESURRECTED (0DTE-dead -> 1-2DTE OOS-positive): **3** ['momentum_morning', 'orb_continuation', 'power_hour']
- SHIPPABLE (clears ALL gates incl L173, n>=20, at 1-2DTE): **0** []

Gate legend: structural = OOS>0 + posQ>=4 + top5<200% + n>=20 + full-drop-top5>0 + IS-first-half>0 + OOS-alone-drop-top5>0 (L173); gate7 = beats random-entry DTE null (L172); gate8 = not a tight-stop truncation artifact (L171). ALL = every gate incl L173.

## vwap_continuation — CONTROL (already LIVE)
_signals: 166_

| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ITM2/-0.08 | 157 | $36.34 | $7.76 PASS | 5/6 | 21.2 | $66.86 | $0.3574 | P | True | ok | $0.0 | 0.0 | **SHIP** |
| 1 | ITM2/-0.08 | 166 | $59.02 | $19.44 PASS | 5/6 | 22.3 | $79.55 | $0.3185 | P | False | ok | $0.0 | 0.0 | - |
| 2 | ITM2/-0.08 | 165 | $66.13 | $21.52 PASS | 4/6 | 29.5 | $117.45 | $0.2502 | P | False | ok | $-342.0 | 1.2 | - |

## momentum_morning — RESURRECTS
_signals: 183_

| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | OTM2/-0.08 | 175 | $-4.68 | $-10.25 FAIL | 1/6 | None | $3.55 | $-0.0289 | F | None | ok | $0.0 | 0.0 | - |
| 1 | ITM2/-0.08 | 181 | $44.01 | $-22.66 FAIL | 3/6 | None | $-39.09 | $-0.0271 | F | None | ok | $550.5 | 2.2 | - |
| 2 | OTM2/-0.08 | 180 | $-16.68 | $-56.83 FAIL | 1/6 | None | $-14.69 | $-0.0881 | F | None | ok | $663.0 | 1.7 | - |

- DTE=0 structural fails: oos_exp=-4.68<=0, pos_q=1/6<4, top5_day_pct=None, drop_top5_full=-6.67<=0, oos_drop_top5=-10.25<=0(L173)

- DTE=1 structural fails: pos_q=3/6<4, top5_day_pct=None, drop_top5_full=-33.07<=0, is_first_half=-39.09<=0, oos_drop_top5=-22.66<=0(L173)
- DTE=1 **de-concentration FAILED (stays L173-fragile)** (must re-clear FULL bar, causal only — no outcome-based filtering):
    - drop_top1_oos_day: n=180 oos_n=58 oos/tr=$16.12 oos-dropT5=$-30.31 full-dropT5=$-35.81 posQ=3 IS1H=$-39.09
    - side=C_only: n=97 oos_n=32 oos/tr=$31.58 oos-dropT5=$-85.44 full-dropT5=$-54.44 posQ=3 IS1H=$-60.09
    - side=P_only: n=84 oos_n=27 oos/tr=$58.74 oos-dropT5=$-25.47 full-dropT5=$-34.66 posQ=2 IS1H=$-12.3

- DTE=2 structural fails: oos_exp=-16.68<=0, pos_q=1/6<4, top5_day_pct=None, drop_top5_full=-34.59<=0, is_first_half=-14.69<=0, oos_drop_top5=-56.83<=0(L173)

## orb_continuation — RESURRECTS
_signals: 123_

| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ITM2/-0.5 | 113 | $18.19 | $-21.98 FAIL | 4/6 | 106.6 | $24.79 | $0.0515 | F | None | ok | $0.0 | 1.8 | - |
| 1 | ITM2/-0.5 | 123 | $183.31 | $-3.9 FAIL | 2/6 | 249.0 | $-6.06 | $0.042 | F | None | ok | $-759.0 | 17.9 | - |
| 2 | ATM/-0.5 | 123 | $200.31 | $-99.71 FAIL | 3/6 | 785.4 | $-17.84 | $0.0159 | F | None | ok | $-6703.5 | 22.8 | - |

- DTE=0 structural fails: drop_top5_full=-1.14<=0, oos_drop_top5=-21.98<=0(L173)

- DTE=1 structural fails: pos_q=2/6<4, top5_day_pct=249.0, drop_top5_full=-46.9<=0, is_first_half=-6.06<=0, oos_drop_top5=-3.9<=0(L173)
- DTE=1 **de-concentration FAILED (stays L173-fragile)** (must re-clear FULL bar, causal only — no outcome-based filtering):
    - drop_top1_oos_day: n=122 oos_n=44 oos/tr=$131.56 oos-dropT5=$-16.65 full-dropT5=$-54.04 posQ=2 IS1H=$-6.06
    - side=C_only: n=65 oos_n=25 oos/tr=$31.49 oos-dropT5=$-173.37 full-dropT5=$-148.95 posQ=2 IS1H=$-61.17
    - side=P_only: n=58 oos_n=20 oos/tr=$373.08 oos-dropT5=$64.64 full-dropT5=$8.49 posQ=3 IS1H=$54.3

- DTE=2 structural fails: pos_q=3/6<4, top5_day_pct=785.4, drop_top5_full=-104.65<=0, is_first_half=-17.84<=0, oos_drop_top5=-99.71<=0(L173)
- DTE=2 **de-concentration FAILED (stays L173-fragile)** (must re-clear FULL bar, causal only — no outcome-based filtering):
    - drop_top1_oos_day: n=122 oos_n=44 oos/tr=$96.59 oos-dropT5=$-117.19 full-dropT5=$-113.24 posQ=3 IS1H=$-17.84
    - side=C_only: n=65 oos_n=25 oos/tr=$-126.85 oos-dropT5=$-323.7 full-dropT5=$-224.64 posQ=1 IS1H=$-84.13
    - side=P_only: n=58 oos_n=20 oos/tr=$609.25 oos-dropT5=$-8.58 full-dropT5=$-51.82 posQ=4 IS1H=$54.77

## power_hour — RESURRECTS
_signals: 190_

| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ITM2/-0.08 | 187 | $24.16 | $1.0 PASS | 3/6 | 207.0 | $2.36 | $0.0341 | F | None | BAD | $0.0 | 3.2 | - |
| 1 | ITM2/-0.08 | 188 | $23.51 | $-74.54 FAIL | 2/6 | None | $-111.12 | $-0.1242 | F | None | ok | $-10177.8 | 19.7 | - |
| 2 | OTM2/-0.08 | 186 | $16.95 | $-136.94 FAIL | 2/6 | None | $24.48 | $-0.0024 | F | None | ok | $-1080.6 | 18.8 | - |

- DTE=0 structural fails: pos_q=3/6<4, top5_day_pct=207.0, drop_top5_full=-3.85<=0

- DTE=1 structural fails: pos_q=2/6<4, top5_day_pct=None, drop_top5_full=-93.53<=0, is_first_half=-111.12<=0, oos_drop_top5=-74.54<=0(L173)
- DTE=1 **de-concentration FAILED (stays L173-fragile)** (must re-clear FULL bar, causal only — no outcome-based filtering):
    - drop_top1_oos_day: n=187 oos_n=54 oos/tr=$-32.72 oos-dropT5=$-84.84 full-dropT5=$-96.93 posQ=1 IS1H=$-111.12
    - side=C_only: n=113 oos_n=33 oos/tr=$-37.31 oos-dropT5=$-123.34 full-dropT5=$-133.89 posQ=1 IS1H=$-174.61
    - side=P_only: n=75 oos_n=22 oos/tr=$114.74 oos-dropT5=$-127.02 full-dropT5=$-72.22 posQ=3 IS1H=$-6.82

- DTE=2 structural fails: pos_q=2/6<4, top5_day_pct=None, drop_top5_full=-94.54<=0, oos_drop_top5=-136.94<=0(L173)
- DTE=2 **de-concentration FAILED (stays L173-fragile)** (must re-clear FULL bar, causal only — no outcome-based filtering):
    - drop_top1_oos_day: n=185 oos_n=54 oos/tr=$-50.01 oos-dropT5=$-148.0 full-dropT5=$-97.62 posQ=1 IS1H=$24.48
    - side=C_only: n=113 oos_n=33 oos/tr=$62.9 oos-dropT5=$-138.75 full-dropT5=$-107.61 posQ=2 IS1H=$68.45
    - side=P_only: n=73 oos_n=22 oos/tr=$-51.97 oos-dropT5=$-280.34 full-dropT5=$-111.25 posQ=2 IS1H=$-50.42

## vwap_pullback — no resurrection
_signals: 98_

| DTE | tier/stop | n | OOS/tr | OOS-dropT5 (L173) | posQ | top5% | IS-1H | risk-adj exp/std | struct | gate7 null | gate8 trunc | gap$ | held% | ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ITM2/-0.08 | 93 | $64.77 | $31.41 PASS | 4/6 | 52.6 | $27.12 | $0.2358 | P | True | ok | $0.0 | 0.0 | **SHIP** |
| 1 | ITM2/-0.08 | 98 | $67.78 | $11.31 PASS | 4/6 | 58.1 | $36.58 | $0.186 | P | False | BAD | $-510.0 | 1.0 | - |
| 2 | OTM1/-0.08 | 97 | $54.79 | $1.92 PASS | 4/6 | 68.3 | $-1.34 | $0.2051 | F | None | BAD | $0.0 | 0.0 | - |

- DTE=2 structural fails: is_first_half=-1.34<=0

## Honest caveats

- **Overnight gap risk is modeled, not assumed away.** Held-overnight trades settle at expiry intrinsic on real SPY closes; a chart stop can GAP THROUGH overnight (reason GAP_THROUGH_STOP). The `gap$` column is the dollar contribution of the close-to-open gap to held trades — small/zero means the lift is theta-driven, not gap-driven.
- **Lower gamma at 1-2DTE inflates per-trade variance** (risk-adj exp/std column). A family can add OOS dollars yet have WORSE risk-adjusted return — that is a risk-up tradeoff (J's call per L175), not a clean win.
- **L173 is the decisive de-concentration gate.** A cell can be OOS-positive and still fail because the OOS lift lives in <=5 fat days; removing them turns it negative. Many 1-2DTE flips are exactly this (gap_fade was the canonical example).
- Settlement uses real SPY closes; the DTE cache holds entry-day option bars only, so mid-life option marks are never synthesised — terminal value is pure intrinsic.