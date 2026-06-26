# B8 — Touch-and-Go vs #1 VWAP_Continuation: Matched-Day A/B (Angle V)

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Cell under test: **ITM-2 / CALL / -8% stop** (C29 — test the tier you claim)
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)
- OOS split: IS=2025 / OOS=2026

## VERDICT: **GENUINE_TRIGGER**

On the 67 SHARED call-days, touch-and-go OOS/tr $178.32 BEATS #1 $154.57 (+$23.75/tr), AND touch-and-go OOS-alone drop-top5 $82.01 > 0, AND no truncation (chart-stop-only $100.99 holds sign). The lift is a BETTER ENTRY trigger on the same day-set, not a day-selection relabel.

## Day overlap (the crux — do they trade the same days?)

- #1 vwap_continuation CALL-days: **86**
- S1 touch-and-go CALL-days: **68**
- MATCHED (both fire) CALL-days: **67** (77.9% of #1, 98.5% of touch-and-go)
- #1-only days: 19  |  touch-and-go-only days: 1

## Matched-day head-to-head (SAME days, only the ENTRY differs)

| trigger | n | days | full/tr | OOS/tr | oos_n | OOS-dropT5 | no-trunc (chart-only/tr) | null pass | WR% |
|---|---|---|---|---|---|---|---|---|---|
| #1 vwap_continuation | 64 | 64 | $71.89 | $154.57 | 19 | $55.42 | True ($89.63) | True | 46.9 |
| S1 touch-and-go | 64 | 64 | $86.62 | $178.32 | 19 | $82.01 | True ($100.99) | True | 48.4 |
| **DELTA (TG − #1)** | | | **$14.73** | **$23.75** | | **$26.59** | | | |

## Disjoint-day disclosure (what each trades ALONE — context, not the test)

| trigger-only set | n | days | full/tr | OOS/tr | OOS-dropT5 |
|---|---|---|---|---|---|
| #1-only days | 18 | 18 | $98.58 | $-10.85 | $None |
| touch-and-go-only days | 1 | 1 | $163.2 | $None | $None |

## How to read this

- The test isolates the **entry trigger** from the **day filter**: both columns trade the SAME matched days at the SAME strike/stop/exits; the ONLY difference is WHICH BAR each trigger enters on.
- **GENUINE_TRIGGER** iff touch-and-go OOS/tr > #1 OOS/tr on the matched days AND touch-and-go OOS-alone drop-top5 > 0 AND no truncation (L171/L173).
- **RELABEL** iff the lift washes on the matched days — then B7's +$58 was a different day-set, not a better trigger; do NOT touch the live edge.
- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, not WR alone (OP-14).
