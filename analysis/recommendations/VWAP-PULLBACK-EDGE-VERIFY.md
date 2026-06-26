# VWAP-PULLBACK EDGE-VERIFY — is `vwap_pullback` (H4) a genuine 4th 0DTE edge, or a RE-SKIN of #1?

_Run 2026-06-21 • SAFE research (Sunday, $0, READ-ONLY — no edits to detectors/params/risk_gate/orchestrator/heartbeat, no orders) • real OPRA fills (C1) • byte-for-byte detectors._

## VERDICT: **RESKIN_OF_1** — `vwap_pullback` is a strict same-side SUBSET of LIVE #1 `vwap_continuation`. NOT a new edge.

The DTE survey (`DTE-LIBRARY-SURVEY.md`) flagged `vwap_pullback` at 0DTE ITM-2/-0.08 as a "NEW SHIPPABLE FINDING" — gate-clean (+$64.77/tr, n=93, all 11 gates incl L173 PASS, beats the random-entry null) and absent from production. This study is the dedicated independence-validation that flag asked for. The gates DO reproduce — but the decisive L174 relational test kills it: **every one of its 98 signal days is also a #1 signal day, on the same side.** It is the same trend-ride read through a slightly stricter VWAP-touch lens, not a second edge. Counting it as additive would double-count #1's P&L (the exact anchored-VWAP A3 trap, which was blocked at 0.973 — this is worse, at 1.000).

---

## 1. INDEPENDENCE (the decisive gate, L174) — `_b8_anchored_vwap` overlap convention, OVERLAP_MAX=0.80

vwap_pullback fires **98 signals on 98 days** (one/day). Overlap vs the validated book:

| vs edge | day-overlap (shared/cand) | Jaccard (shared/union) | **same-side day-overlap** | shared / same-side | RESKIN? (≥0.80 same-side) |
|---|---|---|---|---|---|
| **#1 `vwap_continuation`** | **1.000** | 0.590 | **1.000** | 98 / 98 same-side | **YES — RESKIN** |
| #2 `vwap_reclaim_failed_break` | 0.306 | 0.195 | 0.306 | 30 / 30 | no |
| #4 `vix_regime_dayside` | 0.520 | 0.386 | 0.520 | 51 / 51 | no |

**Subset proof (independent re-derivation):** `vwap_pullback_days ⊆ vwap_continuation_days` is `True` — **0 vp-only days** (none of vp's days are outside #1), **0 opposite-side shared days**. Reverse overlap (#1 days that are also vp days) = 0.59, i.e. #1 fires on 68 extra days vp does not (#1's wider 3-bar / 10:30-cutoff entry net catches more of the same trend-day population).

**Why structurally:** both detectors establish the day's side from the first N RTH closes all on one side of session VWAP, then enter on the first in-trend VWAP touch. #1 uses `TREND_BARS=3` + 10:30 cutoff + breakout-or-shallow-dip; vwap_pullback uses `TREND_BARS=6` + no cutoff + a 0.08% VWAP tag. A clean one-sided-VWAP trend day that triggers the stricter vwap_pullback condition necessarily satisfies #1's looser one. vwap_pullback is a proper subset of #1 by construction.

## 2. FULL 11-gate bar at ITM-2/-0.08 (0DTE, re-run from scratch — NOT trusting the survey prose)

Re-ran via `_dte_expansion_sim` (run_cell dte=0 + metrics + clears_bar) + `lib.truncation_guard` + the survey's `dte_null`. The survey's numbers reproduce to the dollar:

| metric | value | gate |
|---|---|---|
| n / oos_n | 93 / 34 | n≥20 ✅ |
| OOS exp/tr | **$64.77** | OOS>0 ✅ |
| exp/tr (full) | $30.94 | — |
| positive quarters | 4/6 | ≥4 ✅ |
| top5 winning-day % | 52.6% | <200 ✅ |
| IS first-half exp | $27.12 | >0 ✅ |
| full drop-top5 | $15.50 | >0 ✅ |
| **OOS-alone drop-top5 (L173)** | **$31.41** (evaluable) | >0 ✅ |
| gate7 random-null (L172) | null max $16.43 / mean $0.30; cell $30.94 > max AND drop5 $15.50 > mean | beats null ✅ |
| gate8 truncation (L171) | chart-stop-only same-strike not negative | not artifact ✅ |
| **ALL 11 gates** | — | **PASS** |

So the gate-clear is REAL (not a survey artifact). It clears in **isolation**. That is necessary but not sufficient (L174): a re-skin and a true edge both produce a green isolation scorecard — only the overlap test (§1) distinguishes them, and it says re-skin.

## 3. RECENCY — freshest ~25 trading days (merged frame, real OPRA fills to 2026-06-18)

| window | n | exp/tr | sign | verdict |
|---|---|---|---|---|
| recent 2026-05-14..06-18 (25 td) | 5 | **−$20.42** | NEGATIVE | **YELLOW** (n=5 < floor 10 — small-n wobble) |
| full-OOS-2026 | 35 | **+$117.27** | POSITIVE | base remains strong |

Recent is small-n-negative against a strongly-positive full-OOS base — same recency profile as #1's book (the standing recency YELLOW flag). Not RED, but not confirmed. Moot given the re-skin verdict: it is #1's exposure either way.

## 4. INCREMENTAL value over the #1+#2+#4 book (real OPRA fills, ITM-2/-0.08, master frame)

| series | daily Sharpe | corr vs vp |
|---|---|---|
| vwap_pullback alone | 0.356 | — |
| existing book #1+#2+#4 | 0.409 | — |
| **book + vwap_pullback** | **0.431** | — |
| corr(vp, #1) | — | **0.389** |
| corr(vp, existing book) | — | **0.464** |

Adding vp nudges book daily-Sharpe 0.409 → 0.431, but it is **correlated** bull-VWAP exposure (corr 0.39 vs #1, 0.46 vs the book), and §1 proves the days are a strict subset of #1's. The marginal Sharpe bump is mostly position-sizing on overlapping #1 days, not diversification — exactly the "more of the same correlated bull-VWAP exposure" the brief warned about. With WP-1 (the touch-and-go entry refinement for #1) and WP-5 (re-strike #1 to ATM/ITM-2) already capturing this population through the live edge, there is nothing additive to ship here.

## Honest caveats (carried forward)

- **The headline +$64.77/tr uses `premium_stop=-0.08`.** The LIVE first-strike rule (L51/L55/C2) trades **chart-stop-only**, where the prior deep ratify (`vwap_pullback_ratify.py`, 2026-06-19) found only **+$14/t (WR 70.7%)** with **rolling-month WF median 0.239 (FAILS ≥0.70)**, and the regime-gate research found NO clean causal gate. This study evaluates the survey's −0.08 cell as posed; even at its best the independence test closes the thread.
- Proxy strikes (nearest-cached, L58) — directionally valid, $ modestly off. Real OPRA fills throughout (C1). SPY-direction ≠ option edge (C3/L58).

## Files

- Scorecard: `analysis/recommendations/VWAP-PULLBACK-EDGE-VERIFY.json`
- Script: `backtest/autoresearch/_vwap_pullback_edge_verify.py` (reuses `infinite_ammo_discovery.detect_vwap_pullback`, `_dte_expansion_sim`, `_b8_anchored_vwap` overlap convention, `recency_check` window, `_edgehunt_vwap_continuation`/`_sub_struct_vwap_reclaim_failed_break`/`_b5_vix_regime_dayside` detectors — all byte-for-byte)
- Closes the "second 0DTE VWAP-family edge" thread opened in `STATUS.md` [2026-06-21 DTE-EXPANSION FOLLOW-UP] and `DTE-LIBRARY-SURVEY.md`.
