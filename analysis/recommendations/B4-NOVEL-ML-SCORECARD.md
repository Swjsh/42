# B4 — Novel-Data + ML Hunt — HONEST Scorecard

**Date:** 2026-06-21 · **Batch:** B4 (novel-data layers + learned-model direction hunt)
**Bar:** standing all-8-gate suite on real OPRA fills (C1) + null_baseline + truncation_guard. OOS = clean calendar split (IS=2025 / OOS=2026).
**Headline:** 0 NEW deployable edges. 1 confirmed DIAGNOSTIC (no new edge expected). 1 promising-but-dormant futures lead. 1 ML reject (but actionable feature ranking). 2 dead/untestable novel-data reads.

---

## Ranked table

| # | Candidate | Kind | Gates | OOS/trade | Verdict | Status |
|---|-----------|------|-------|-----------|---------|--------|
| 1 | **reclaim_null_precision** (diagnostic on edge #2) | diagnostic | **8/8** ✅ | **+$32.33** (n=18) | CONFIRMED — diagnostic, no new edge | Edge #2 stays the live-flip candidate; this REFINES how to size it |
| 2 | **MES/MNQ lead-lag divergence** | novel-data (futures) | 7/8 ❌ (g5) | +$55.23 | FAIL — non-robust (concentration) | DORMANT — most promising novel lead; needs concentration fix |
| 3 | **ML next-K-bar direction classifier** | learned model | 1-2/8 ❌ | **−$22.53** | REJECT | DEAD as a trade; feature ranking is reusable |
| 4 | **Volume-profile POC / value-area** | novel-data | 4/8 ❌ | +$1.49 (artifact) | REJECT — truncation + concentration artifact | DEAD (C3/L58) |
| 5 | **Gamma-wall / max-pain interaction** | novel-data | null (untestable) | n/a | INFEASIBLE — no historical data | DEFERRED — capture accruing |

---

## (a) Reclaim null-precision — CONFIRMED (timing vs selection + buffer plateau)

**This is a DIAGNOSTIC on the already-confirmed dormant edge #2 (`struct_vwap_reclaim_failed_break`), not a new edge.** Independently re-run and reproduced byte-for-byte. Two settled findings:

**PART A — Precision vs selection: the OOS edge is DAY+SIDE SELECTION, NOT trigger-bar timing precision.**
- Against the high-seed (60) bar-randomized **same-day same-side** null, the signal sits **INSIDE** the null band on the OOS(2026) slice for BOTH tiers: ITM-2 z=−0.72 (18th pctl), ATM z=−1.48 (12th pctl).
- Full-sample ITM-2 has only *modest* timing precision (z=1.54, 95th pctl); the ATM rescue cell does not clear even full-sample (z=0.92, < +1σ).
- The coarser coin-flip null is beaten everywhere — that only confirms day-selection, not bar precision.
- OOS is heavily single-regime: the entire +$582 OOS total sits in **Feb 2026** (+$658; Apr/May negative); top-3 OOS days carry it (drop-top3 OOS goes negative −$7.69). This is a FLAGGED CAVEAT the candidate itself stated ("DAY+SIDE SELECTION, not trigger precision" + `oos_lift_within_sameday_null_band` on every cell), not an overclaim.
- **Implication:** size/confidence on edge #2 must rest on **choosing the right trend DAY + SIDE**, NOT on the specific reclaim bar. Do NOT claim bar-level timing alpha.

**PART B — Stop-buffer plateau: $0.25 is a WIDE FLAT PLATEAU, not a spike.**
- Every buffer in {0.10, 0.15, 0.20, 0.25, 0.30} gives **IDENTICAL** results: exp $54.21/trade, OOS $32.33, **8/8 gates**. The knob does not bind inside [0.10, 0.30].
- The rescue's 7/8→8/8 gain came entirely from crossing the **$0.50 boundary**, which flips exactly ONE trade's level-stop (ref buf=0.50: $53.28/trade, OOS $28.39, 7/8).
- **Conclusion:** $0.25 is the *center of a wide flat favorable region* — robust, not fragile. The buffer can sit anywhere ≤ $0.30.

---

## (b) MES/MNQ divergence — did it clear as a NEW futures edge? **NO.**

**FAIL — 7/8 gates, fails gate 5 (drop-top5-days). NOT flip-ready.** But it is the **most promising novel-data lead** of the batch.

- A **genuine, directional asymmetry exists in ONE direction only:** **MES-leads → trade MNQ laggard** is OOS-positive (+$28 to +$82/trade across thresholds), decisively beats the random-entry null (null is NEGATIVE ~−$13/trade; signal beats even the p95-luckiest null), and is **NOT** a truncation artifact (chart-stop + EOD per-trade also positive ~$28). It passes the two HARDEST gates (beats-null at p95, no-truncation).
- **The reverse (MNQ-leads → trade MES) is weak/dead** → NDX is the laggard that catches up, not SPX.
- **Killer:** classic **C4 concentration**. WR only ~34%, top-5 winning days = **115%** of total P&L; dropping them flips per-trade to **−$4.70** (fails gate 5). Lose small most days, occasionally catch one huge MNQ catch-up runner. **0 of 12 cells clear all 8 gates** → no cherry-pick rescue under the standing all-gates bar.
- **Best cell:** MES-leads → MNQ laggard, divergence threshold 0.0015 (0.15% normalized-return spread), ATR-trail exit (chart-stop floor + chandelier 2.5×), EOD flat.
- **Verdict:** DORMANT. Real directional signal, but a low-WR fat-tail strategy whose entire expectancy lives in ~5 days. Needs a **concentration fix** (position-cap, day-filter, or volatility-regime gate) before re-test toward deployment.

---

## (c) ML direction classifier — did it beat baseline OOS + what features matter?

**Baseline: YES (marginally). Trade edge: NO. REJECT.**

- **Beats baselines OOS on raw direction:** LR 53.0% / GBM 51.6% vs coin-flip 50.0% / train-majority 51.3% (beats BOTH, OOS, no leakage; strict walk-forward train-2025 → test-2026).
- **But that does NOT translate to a 0DTE option edge** — textbook **C3 / L58**. The top-decile high-probability subset (64 distinct-day OOS picks, 56C/8P) **loses on real OPRA fills: OOS −$22.53/trade** at survivor ITM-2/−8% (−$3.38 at ATM). Clears only **1-2 of 8 gates** (g4 n≥20, g8 no-truncation — the latter trivially, since it loses outright). Fails g1, g2 (posQ 1/6), g3, g5 (−$24.41), g6 (IS-half −$10.15), g7 (null). A ~53% 30-min hit rate is below the break-even WR a 0DTE bracket needs after theta/delta/spread.
- **Feature importance (ACTIONABLE for future feature selection):**
  1. **VIX (level + slope) — DOMINANT** in both models (GBM split-freq 0.48; LR |std-weight| 0.090)
  2. VWAP-distance
  3. Time-of-day
  4. Prior-bar returns
  5. Structure label
  - **Near-DEAD:** RSI(2/14) and ribbon-stack carry ~zero weight.
- **Takeaway:** VIX character is the strongest learnable signal (consistent with C5). RSI / ribbon-stack are noise for direction prediction — drop them from future feature sets.

---

## (d) Gamma-wall & volume-profile verdicts

**Gamma-wall / max-pain — INFEASIBLE (untestable, NOT tested-and-failed).**
- The dealer gamma surface (per-strike OI + per-contract gamma across the full chain) exists for **exactly 1 day** (`journal/gex-archive`, 2026-06-19; `Gamma_GexCapture` started banking that day). OPRA bars carry only OHLCV/vwap/trade_count — **no OI, no gamma**, and OI (daily EOD) is not reconstructable from intraday price.
- Engine's own `gex_regime.assess_backtest_feasibility()` returns `can_backtest_now=False`. **Refused to fabricate** a proxy backtest (banned, C4/L171, OP-20) → **0 trades, all 8 gates null** (untestable), not 0 (failed).
- **Re-run trigger (documented):** ≥ **60** GEX-archive days with `status==ok` → mark walls/max-pain per day (reuse `lib.engine.gex_regime` + add max-pain), detect causal wall-interaction entries, fill via `simulate_trade_real`, split MAGNET (long-gamma) vs REJECTION (short-gamma) by `net_gex_sign`, run full suite. Capture is **already running** — this is the cleanest deferred lead.

**Volume-profile POC / value-area — REJECT (C3/L58).**
- Per-trade-best cell (developing profile, ATM, −8% stop, n=1733) clears only 4/8 and fails 4 decisively: drop-top5 per-trade NEGATIVE (−$0.28, day-concentrated), IS-first-half −$2.36 (edge only late in-sample), does NOT beat random-entry null (+$1.19 vs null mean +$2.25 — random strictly better), and is a **truncation artifact** (same-strike chart-stop-only −$24.75/trade — the −8% stop manufactures the positive number).
- **21% real-fills WR vs the lore's ~70% reversion narrative** is the textbook C3/L58 tell. Every cell at any honest (chart-stop-only) stop is deeply negative across both prior-day and developing variants. DEAD.

---

## SHIP recommendation (per standing authorization)

**No new edge crosses the auto-ship bar in B4 — so there is nothing NEW to flip live.**

- **Edge #2 (`struct_vwap_reclaim_failed_break`) remains the confirmed dormant flip-ready candidate.** B4 did NOT discover a new edge; it REFINED how edge #2 should be sized and confirmed its rescue knob is robust:
  - **Config (ATM Safe-2 rescue cell):** strike_offset=0 (ATM), tp1=0.30, premium_stop=−8%, level_stop_buffer = **$0.25** (anywhere in [0.10, 0.30] is identical, 8/8 gates). n=76, exp $54.21, OOS $32.33, posQ 5/6, beats_null, truncation_safe. ITM-2 anchor exp=$93.67 / oos=$72.11.
  - **Tradeable instrument/strike:** SPY 0DTE, ATM single-leg directional on the Safe-2 account (OTM-2 tier maps to the ATM rescue cell), or ITM-2 on the anchor tier.
  - **Sizing discipline (the B4 lesson):** confidence/size on **day+side selection quality** — the right trend day and the right side — NOT on the specific reclaim bar. Do NOT advertise bar-level timing alpha. Respect the OOS regime-concentration caveat (Feb-2026-heavy) when sizing.
  - **Wiring is a DELIBERATE step:** build dormant-flip-ready + adversarial swarm review BEFORE enable, exactly as edge #2 was handled. B4 does not change edge #2's flip status — it sharpens the sizing thesis.

---

## NEXT-ITERATION recommendation (directive: keep testing — all-night)

**Primary (highest expected value): rescue the MES/MNQ divergence lead — it is the only NEW signal with a validated directional asymmetry.**
Re-test **MES-leads → MNQ-laggard** (threshold 0.0015) with a **concentration fix** to attack the gate-5 failure:
1. **Volatility-regime gate** — restrict entries to high-ATR / VIX-elevated sessions where catch-up runners cluster (the fat tail likely lives in a regime; gate to it).
2. **Position-cap / per-day-trade-cap** — cap to 1 entry/day to test whether the edge survives without the multi-entry pile-on on the 5 monster days.
3. **Day-filter via the divergence magnitude** — only take the top-quartile divergence-spread bars (bigger lead → bigger laggard snap), re-measure drop-top5.
Re-run the full 8-gate suite per variant. If any variant flips gate 5 positive while holding beats-null + no-truncation, it becomes a real futures candidate.

**Secondary:** Feed the B4 feature ranking back into the signal layer — **VIX (level+slope) + VWAP-distance + time-of-day** are the live-weight features; **drop RSI(2/14) and ribbon-stack** from any future direction model. Re-run the learned model on the **MES/MNQ futures** target (point-P&L, no theta) instead of 0DTE options — the C3/L58 theta/delta tax is what killed the option version; a point-based instrument may let the marginal 53% direction edge survive.

**Deferred (no action needed — capture running):** Gamma-wall / max-pain re-fires automatically once `journal/gex-archive` reaches ≥ 60 `status==ok` days.
