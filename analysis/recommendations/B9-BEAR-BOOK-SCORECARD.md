# B9 — REGIME-CONDITIONAL BEAR BOOK (Angle B) — Scorecard

_Generated 2026-06-21 — pure-Python real-fills (C1), $0, markets closed._

## The question

All three real edges (#1 vwap_continuation LIVE, #2 reclaim, #4 vix_regime) are VWAP-native and **bull-biased**. The robustness gap: **is there a bearish VWAP-native structural edge that works WHEN GATED TO A BEARISH REGIME** — the book we want on hand for when the tape flips?

**Regime gate (causal):** day-trend side DOWN (first 3 closes below VWAP) AND entry close below the ribbon slow EMA AND ribbon stack != BULL.

## Standing bar (11 gates)

g1 OOS/trade>0 · g2 >=4/6 posQ · g3 top5<200% · g4 n>=20 · g5 drop-top5>0 · g6 IS-half>0 · g7 beats-null (L172) · g8 no-truncation (L171) · g9 **OOS-ALONE drop-top5>0 (L173)** · g10 **independence vs #1 <0.80 overlap (L174)** · g11 **no-regression: skipped days net<=0 (L174)**

## 0DTE real-fills (the production authority)

| structure | tier | n | OOS n | OOS/trade | posQ | drop5 | OOS-alone5 | overlap#1 | skipNet | gates | verdict |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| BEAR_CONT | ATM_safe2 | 54 | 15 | $18.32 | 3/6 | $-15.95 | $-60.62 | 0.0 | $889.8 | 7/11 | 7/11 |
| BEAR_CONT | ITM2_bold | 54 | 15 | $39.03 | 4/6 | $-19.22 | $-74.34 | 0.0 | $889.8 | 8/11 | 8/11 |
| BEAR_FBO | ATM_safe2 | 41 | 13 | $23.35 | 3/6 | $-29.98 | $-56.1 | 0.0 | $2591.4 | 4/11 | 4/11 |
| BEAR_FBO | ITM2_bold | 41 | 13 | $42.42 | 4/6 | $-25.73 | $-65.85 | 0.0 | $2591.4 | 5/11 | 5/11 |
| BEAR_RIDE | ATM_safe2 | 5 | 2 | $24.0 | 3/3 | $None | $None | 0.0 | $3176.0 | 4/11 | 4/11 |
| BEAR_RIDE | ITM2_bold | 5 | 2 | $41.7 | 2/3 | $None | $None | 0.0 | $3176.0 | 3/11 | 3/11 |

## Futures point-P&L (theta-free directional check, SHORT only)

| symbol | structure | n | OOS/trade | full/trade | posQ | drop5 | core gates |
|---|---|--:|--:|--:|--:|--:|---|
| MES | BEAR_CONT | 56 | $-31.89 | $-2.87 | 2/6 | $-37.61 | no |
| MES | BEAR_FBO | 46 | $-26.88 | $1.62 | 2/6 | $-36.98 | no |
| MES | BEAR_RIDE | 6 | $-48.62 | $-10.85 | 1/6 | $-96.58 | no |
| MNQ | BEAR_CONT | 56 | $1.43 | $-23.83 | 2/6 | $-73.97 | no |
| MNQ | BEAR_FBO | 44 | $138.52 | $22.26 | 4/6 | $-58.41 | no |
| MNQ | BEAR_RIDE | 6 | $-73.48 | $-29.02 | 1/6 | $-160.6 | no |

## OP-16 anchor fidelity — BEAR_RIDE (J's BEARISH_REJECTION_RIDE_THE_RIBBON)

- **edge_capture = $0.0** (WIN-day P&L $0.0, LOSS-day loss $0.0) -> **FAIL**
- Per-anchor:
  - 2026-04-29 (WIN): took=False pnl=$0.0
  - 2026-05-01 (WIN): took=False pnl=$0.0
  - 2026-05-04 (WIN): took=False pnl=$0.0
  - 2026-05-05 (LOSS): took=False pnl=$0.0
  - 2026-05-06 (LOSS): took=False pnl=$0.0
  - 2026-05-07 (LOSS): took=False pnl=$0.0
- _Caveat: anchors are 2026 (OOS) dates -> this is a FIDELITY check, not independent OOS._

## Verdict

**NO standalone bear edge clears the 11-gate bar in this 2026 bull window.** This is the expected/honest outcome — puts fight positive drift + faster theta. The regime gate confines puts to down-days but the bull tape leaves too few clean continuation down-days to build a positive-expectancy real-fills book.

Least-bad standalone cell: **BEAR_FBO/ITM2_bold** at OOS $42.42/trade (oos_n=13) — still fails the bar.

**Robustness value:** the harness is now on file. When the regime turns (sustained down-trend tape), re-running `_b9_bear_book.py` will re-test these exact structures on the new OOS window without rebuild. A regime-gated bear book is the robustness hedge the all-bull edge stack is missing.
