# H1 — VWAP-Side Alignment Gate

**Rank:** 1 of 8 · **Score:** 9.0 · **Seam:** J real-fills (richest ground truth) · **Status:** PROPOSAL (test, do not ship)

---

## The setup / signal

A binary **direction-vs-VWAP alignment** gate applied at entry-bar evaluation:

- **Trend / continuation / breakout entries** (RIDE_THE_RIBBON, level-break, ORB, BOS): require the entry to be on the **correct side of session VWAP** for its direction — calls only when `close > session_VWAP`, puts only when `close < session_VWAP`.
- **Reversal-off-extreme entries** (BEARISH_REJECTION fading a session high, the H6 mirror): the *opposite* — the fade is *into* an extreme that has pushed to the far side of VWAP (puts faded when price is stretched *above* VWAP; calls when stretched *below*). The gate is **role-aware**, not a blanket "trade with VWAP."

Session VWAP = cumulative `sum(typical_price * volume) / sum(volume)` from 09:30 ET reset, computed look-ahead-free from closed 5m bars only.

## The insight (why it should have edge)

From `markdown/0dte/J-WEBULL-EDGE-2021-2023.md` step-3 archetype table (the real-fills winner study):

> "**VWAP alignment is near-universal.** In the 7 trend/continuation/breakout winners, the entry was on the correct side of session VWAP for the direction. The 2 reversal winners (3/14, 5/12) deliberately faded price that had pushed *above* VWAP into a session high."

That is **9 of 9** of J's top real winners conforming to a single, simple, role-aware VWAP rule — the strongest single-feature regularity in his entire documented winning book. L168 explicitly lists it as one of two findings that **"deserve a causal + balanced-OOS + anchor-no-regression A/B before any gate."** Mechanistically it is sound: VWAP is the session's volume-weighted fair value and the reference institutional desks anchor to; entering trend trades with it (and fading exhaustion stretched far from it) aligns with the dominant order flow rather than against it.

## EXACT backtest to validate

1. **Feature:** add `session_vwap` + `dist_to_vwap_dollars` + `vwap_side` ({above,below}) to the bar-feature builder used by `backtest/lib/watchers/*` (compute once per day, reuse). Unit-test against a hand-computed VWAP for one historical session (TDD per L03).
2. **Grid (Stage-1):** for each existing live/eligible setup family, evaluate 3 arms — `gate=off` (baseline), `gate=trend_aligned` (require same-side VWAP for trend setups), `gate=role_aware` (trend same-side + reversal far-side). Strike offsets {-2,-1,0,+1}; stop {chart-stop-only -0.99, v15 -0.08} so the truncation cross-check has both poles.
3. **Data:** `backtest/data/spy_5m_2025-01-01_2026-06-16.csv` + VIX. IS = through 2026-Q1, OOS = 2026-Q2 held out.
4. **Real-fills:** top cell through `*_real_fills_validate.py` (OPRA) — C1 authority for the WR/expectancy verdict.
5. **Anchor (OP-16):** `j_edge_tracker.score_candidate` — gate must keep 4/29, 5/01, 5/04 (all were correct-VWAP-side puts in a downtrend → should PASS the trend-aligned arm) and must not add 5/05/5/06/5/07 losers.
6. **Guards:** L171 `cross_check_grid` (no sign inversion at chart-stop-only), L172 `null_gate` (beat null MAX), per-quarter net-positive (>=4/6), top5_pct <= 200%.
7. **Scorecard:** `analysis/recommendations/h1-vwap-side-alignment.json` with the per-arm edge_capture, real-fills exp, null_pass, truncation_pass, and a `vwap_side_winrate` table stratifying WR by aligned/anti-aligned.

## Kill criteria (reject if ANY)

- The `role_aware` arm's `edge_capture < baseline` (gate removes a J winner — likely if VWAP feature mis-signs the reversal role).
- Top cell positive at v15 stop but **negative at chart-stop-only same strike** (L171 truncation artifact → REJECT).
- Signal per-trade fails to beat the random-entry null MAX (L172 → "the bracket, not the read").
- Aligned-vs-anti-aligned real-fills expectancy gap < ~$10/trade (no separation → VWAP side carries no option edge on SPY-now, only SPX-2021-23; C22 non-transfer).
- OOS-Q2 per-trade <= 0 or per-month-normalized test/train < 0.5.

## Expected edge_capture x feasibility

**edge_capture HIGH** (directly encodes J's #1 winner trait; should *raise* anchor capture, not threaten it). **feasibility HIGH** (one deterministic feature, all data on hand, isolatable as a pure gate). Top-ranked because it is the best edge-per-unit-effort in the project and L168 pre-cleared it for testing.

## Disclosure (OP-20)

J's VWAP finding is **n=9 SPX 2021-23** — an anchor-context regularity, not a validated SPY-now detector (the doc says so verbatim). This A/B is the validation; it does NOT assume the result. Account-scaling, concentration, and regime-sensitivity tables to be filled in the scorecard.
