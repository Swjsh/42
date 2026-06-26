# H3 — Market-Structure BOS/CHoCH as an ENTRY Signal

**Rank:** 3 of 8 · **Score:** 7.5 · **Seam:** entry structure (the blueprint's #1 diagnosed gap) · **Status:** PROPOSAL (test, do not ship)

---

## The setup / signal

Promote the **already-shipped** market-structure detector from WATCH_ONLY to an actual entry trigger:

- **Break of Structure (BOS):** in an established uptrend (sequence of HH/HL), price makes a new HH after a HL → trend-continuation **call** entry on the BOS bar close (mirror: LL after LH in a downtrend → put). This is the structural form of RIDE_THE_RIBBON but driven by *price swings*, not the lagging ribbon.
- **Change of Character (CHoCH):** the first LH/LL that breaks an uptrend's HL (or the first HH/HL that breaks a downtrend) → early reversal entry, tighter stop at the broken swing.

Detector exists: `backtest/lib/watchers/market_structure_watcher.py` + `backtest/lib/.../market_structure.py` (HH/HL/LH/LL + BOS + CHoCH), gym-validated (v46, gym 89/89 per memory `project_chart_master_ta_layer`). Today it only *watches*.

## The insight (why it should have edge)

This is the single most-cited architectural gap in the project. From memory + the autonomy blueprint:

> "2026-06-20: engine read trend from ribbon NOT price structure (the #1 gap); shipped market_structure.py (HH/HL/LH/LL+BOS+CHoCH) ... specs/ARCHITECTURE.md is STALE."

J trades the structure *by eye* — "are we making higher highs / what's the structure" is a first-class question the `chart-read` skill answers. The ribbon is a **lagging** EMA-stack proxy for trend; BOS/CHoCH read trend from the actual swing sequence, which leads the ribbon. The 5/07 -$45 loss (`mistakes.md`) is the canonical evidence: the engine went long on a single-bar ribbon-bull reclaim while price was printing **three consecutive lower highs** at a broken level — a CHoCH the engine literally could not see. A structure-aware entry would have read the LH sequence and refused (or reversed) that trade.

## EXACT backtest to validate

1. **Wire the watcher as a candidate trigger** in a sandboxed grinder (NOT the live engine): map `BOS_LONG/BOS_SHORT/CHoCH_LONG/CHoCH_SHORT` into the backtest trigger taxonomy (L103/L153 — backtest trigger names must map to live filter categories).
2. **Look-ahead audit FIRST** (C6, L14/34/57/61): swing-point confirmation must use only closed prior bars; a swing high is confirmed only after N bars fail to exceed it. Unit-test that no entry uses a swing not yet confirmed at the entry bar. This is the highest-risk part — get it wrong and the whole result is look-ahead.
3. **Grid:** entry on {BOS only, CHoCH only, BOS+CHoCH} x swing-lookback {3,5,7 bars} x strike {-2,-1,0} x stop {-0.99 chart-stop-at-broken-swing, -0.08}.
4. **Data/OOS:** `spy_5m_2025-01-01_2026-06-16.csv` + VIX; IS through Q1, OOS Q2.
5. **Real-fills + anchor:** top cell through OPRA validator; `j_edge_tracker` — BOS-short should *capture* 4/29/5/01/5/04 (all downtrend continuation puts) and CHoCH should *refuse* the 5/07 counter-trend bull loss → expect `edge_capture >= baseline` AND fewer J-loser-class entries.
6. **Guards:** L171 truncation, L172 null-MAX (especially important — a structure entry must beat a coin flip, or it's just the bracket), per-quarter >=4/6, top5 <= 200%.
7. **Scorecard:** `analysis/recommendations/h3-market-structure-entry.json` with a stratification of P&L by trigger type and a head-to-head vs the current ribbon-only entry on the same days.

## Kill criteria (reject if ANY)

- Look-ahead audit fails (any entry references an unconfirmed swing) → fix-or-kill before any P&L is trusted.
- Per-trade fails to beat the null MAX (L172) → BOS detections are firing on noise, not structure (C27: a detector firing >80% of days measures noise — verify firing rate < ~40% of days).
- `edge_capture < baseline` (BOS-short missed a J winner, or CHoCH added a loser).
- Truncation cross-check inverts at chart-stop-only.
- Firing rate so high it's indistinguishable from "always on" (C27).

## Expected edge_capture x feasibility

**edge_capture HIGH** (the architectural fix J's whole TA-layer push targets; should both capture trend winners AND refuse counter-trend losers like 5/07). **feasibility MED** (detector + gym validation already exist, but promoting WATCH→ENTRY needs a careful look-ahead audit and trigger-taxonomy mapping — non-trivial but bounded). Ranked #3 because the payoff is structural/strategic, slightly higher execution risk than the two pure-feature gates above.

## Disclosure (OP-20)

Detector is gym-correct but its **entry edge is unvalidated** — gym tests detection correctness, not P&L. C24 caveat applies: a clean BOS on an anchor day does not prove the BOS *population* is profitable; validate IS population WR before any live promotion. Ships behind the OP-21 gate (3+ live observations) even on a passing backtest.
