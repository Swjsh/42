# VWAP_TREND_PULLBACK — regime-gate research verdict (2026-06-19)

**Question (profit edge #2):** the H4 VWAP-trend-pullback edge is held back ONLY by
BIMODALITY — per the walk-forward it bled 4 OOS months (2025-07..10) then went 7
straight positive (2025-11..2026-05). Does a CAUSAL regime gate cleanly separate the
good periods from the bad, turning it into a 2nd LIVE +EV edge — or can it not be
cleanly done?

**Verdict: BASE-SIZE / KEEP-DORMANT — NONE clean.** No causal regime gate makes the
edge meet OP-22 on the exit config the live detector actually trades. A false 2nd edge
is worse than none. Details below.

- Harness: [`backtest/autoresearch/vwap_pullback_regime_gate.py`](../../backtest/autoresearch/vwap_pullback_regime_gate.py) (diagnosis + gate sweep, both exit configs)
- Anti-overfit: [`backtest/autoresearch/vwap_pullback_gate_own_oos.py`](../../backtest/autoresearch/vwap_pullback_gate_own_oos.py) (threshold-own-OOS)
- Scorecards: [`analysis/recommendations/vwap-trend-pullback-regime-gate.json`](../../analysis/recommendations/vwap-trend-pullback-regime-gate.json), [`analysis/recommendations/vwap-trend-pullback-gate-own-oos.json`](../../analysis/recommendations/vwap-trend-pullback-gate-own-oos.json)

---

## Finding 0 (load-bearing) — the scorecard edge and the LIVE edge are different exits

The ratify scorecard `vwap-trend-pullback-LIVE.json` headline (**+$45.88/t, WR 42.4%**,
the bimodal WF median 1.679) was computed with **premium_stop = −0.08** — the discovery
`simulate_signals` passes no override, so it inherits `simulate_trade_real`'s −0.08
default. But the **live watcher trades CHART-STOP-ONLY** (`vwap_trend_pullback_watcher.py
DEFAULT_PREMIUM_STOP_PCT = −0.99`, per L51/L55/C2), and the heartbeat wiring proposal
says "STOP: chart/structural ONLY (premium stop DISABLED)."

On the **live chart-stop-only** config the ungated edge is **+$14.03/t, WR 70.7%**, and
its rolling-month **WF median = 0.239 — FAILS the ≥0.70 gate**. So the "strongest edge"
framing rests on an exit the engine would not trade. (This is the C29/L149 pattern: exit
knobs validated on one config don't transfer. The chart-stop-only config needs its own
WF/OOS pass before any live order, gate or no gate.)

Both configs are evaluated throughout; the **live verdict uses chart-stop-only**.

---

## Finding 1 — the bimodality diagnosis is INVERTED from the trend-day prior

VWAP-pullback is structurally a trend-day setup, so the prior was "it works on trending
days, fails in chop." The data says the **opposite**. Losing months (2025-07..10) vs
winning months, on causal at-entry features:

| feature (median) | losing months | winning months |
|---|---|---|
| VIX | **16.6** (lower) | 18.3 |
| intraday ADX-like trend strength | **57.4** (higher) | 51.8 |
| realized vol (bps/bar) | **6.2** (lower) | 8.1 |
| morning move % | 0.0024 | 0.0033 |
| regime_book cell | 44% BULL_TREND, 36% NEUTRAL | **40% HIGH_VOL**, 24% BULL_TREND |

The edge **bled on calm, low-VIX, high-ADX trend days** and **worked in higher-VIX /
high-vol periods**. So ADX, realized-vol, range-expansion, and the "trade only the
trend cells" gate all point the WRONG way — they can't separate good from bad. The
bimodality is a regime-**ERA** split, not a clean structural-feature split.

---

## Finding 2 — gate sweep (both exit configs)

Winner bar: on the gated subset — `all_sub_windows_positive` (kills the bimodality) AND
`oos_sign_stable` AND n_kept ≥ 35 AND retention ≥ 0.40 AND DSR≠FAIL AND both_dirs+ AND
robust-to-drop-top-5.

- **Live (chart-stop-only): ZERO winners.** Best candidates all fail:
  - `vix_lt_18`: exp only **+$5.2**, all-sub+ = **False**, robust = **False**.
  - `vix_lt_17`: exp **−$3.3**, both-dirs+ = **False**.
  - `vix_falling`: exp +$62.3 and both-dirs+ and OOS-stable and DSR PASS — **but** first
    sub-window is **−$62** (all-sub+ = False), drop-top-5 mean is **−$11** (not robust),
    keeps only **24 trades** (8 puts), and its "clean monthly WF" is a small-denominator
    artifact (OOS months are n=1 each — one trade defines a "positive month").
- **Scorecard −8% config: one winner, `vix_lt_18`** (keep 47, all-sub+, OOS-stable, DSR
  PASS, both-dirs+). But see Finding 3 — it does not survive the anti-overfit test, and
  it's on the exit the engine doesn't trade.

GEX was **excluded as a gate** because it is not backtestable on our data (no historical
full-chain OI+gamma archive; `gex_regime.assess_backtest_feasibility`). Every gate tested
uses SPY+VIX features we have historically AND compute live.

---

## Finding 3 — anti-overfit: the one "winner" is a grid artifact, not a real cut

Threshold-own-OOS (derive `VIX < X` on the IS half ONLY, apply unseen to OOS):

- On **both** configs the IS-optimal threshold (with ≥20 IS trades) is **X ≈ 22** — i.e.
  "barely filter anything" (keeps 75/92). The IS expectancy is **flat** across VIX<17/18/
  19/22 on the −8% config; there is no IS signal that "18 is special."
- `vix_lt_18` looked like a winner only because its **OOS** happened to land all-sub-
  positive — that is selecting on OOS, the exact overfit trap.
- On the **live chart-stop-only** config a VIX gate is **anti-correlated IS↔OOS**: VIX<18
  has IS expectancy **−$26.2** while its OOS is positive (C22 inversion — gates proven on
  one regime don't transfer). Definitively not a generalizing edge.

---

## What was (and was NOT) wired

- **NOT wired:** no `vwap_trend_pullback_regime_gate` param, no gate logic. Wiring a gate
  that only "works" on a non-traded exit config as an OOS-selected grid artifact would be
  encoding a non-edge (the precise foot-gun this research exists to prevent).
- **Unchanged:** `VWAP_TREND_PULLBACK` stays **WATCH_ONLY** — detector built + parity-
  tested + registered (observation only), `regime_book` slot stays WATCH_ONLY. No live
  order path. Zero behavior change.

### Forward paths (J's call, not auto-shipped)

1. **Fix the exit first.** The live chart-stop-only config fails WF (0.239) on its own.
   Either re-validate chart-stop-only head-on, or adopt the −8% premium stop *for this
   setup specifically* and re-ratify the base edge — THEN revisit a regime gate. The
   exit mismatch (Finding 0) is the higher-priority defect.
2. **Accrue live data.** Let the WATCH archive grow; revisit a gate with more samples
   (n=92 over 17 months is modest; the OOS months are 4–9 trades each).

A false 2nd edge is worse than none. Edge #2 is **not** shippable from this research.
