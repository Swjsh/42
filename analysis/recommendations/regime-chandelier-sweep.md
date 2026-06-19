# Regime-Conditional Chandelier Sweep — exit/regime leverage on BEARISH_REJECTION

**Date:** 2026-06-19 · **Window:** 2025-01-01 .. 2026-05-29 (OPRA real-fills) · **Status:** RESEARCH / propose-only (Rule 9)
**Scorecard JSON:** [`regime-chandelier-sweep.json`](regime-chandelier-sweep.json) · **Harness:** `backtest/autoresearch/sweep_regime_chandelier.py`
**Knobs added (opt-in, default OFF):** `lib.simulator_real.simulate_trade_real(profit_lock_trail_basis, profit_lock_trail_underlying_pct, profit_lock_trail_pct_by_vix, profit_lock_trail_underlying_pct_by_vix, entry_vix)`

## Verdict (headline)

**The peer-reviewed finding does NOT transfer to 0DTE. The regime-conditional / underlying-move chandelier is the WRONG direction here — a TIGHTER fixed trail wins.** `any_promote_candidate = True`, but the promoted variant is the opposite of what Kim-Tse-Wald predicts.

- **`fixed_premium_15` (15% trail, vs the v15 20%) is the clean PROMOTE-CANDIDATE on BOTH strikes.** It beats the production chandelier on total P&L and expectancy, holds anchor-no-regression, and *improves* DSR vs baseline:
  - **ATM:** total +$1,071.7 → **+$2,430.4** (Δ **+$1,358.8**), exp +$7.94 → +$18.00, DSR 0.168 → **0.343**, PSR 0.69 → 0.85.
  - **ITM2:** total −$601.2 → **+$574.4** (Δ **+$1,175.6**, flips the sign), exp −$4.89 → +$4.67, DSR 0.046 → **0.105**, PSR 0.41 → 0.58.
- **Every WIDER and every REGIME-CONDITIONAL variant LOSES on both strikes** — the literal finding (wider trail in high vol) is the worst family here: `regime_premium_WIDE_HIVOL` = −$605 ATM / −$1,090 ITM2; trail 25%/30% both negative.
- **Underlying-move trail is mixed and direction-confirms the same story:** the *tight* `underlying_fixed_0.30pct` promotes (it's effectively a tight trail: +$1,355 ATM / +$799 ITM2), while the wider 0.50% and the underlying-regime map both lose. So "trail the underlying" per se is not the lever — *tightness* is.

**Why the literature inverts for us:** Kim-Tse-Wald is about multi-day/-week trend following, where a wide vol-scaled trail keeps you in a position whose expected drift is positive while it shakes out noise. 0DTE long premium has the opposite payoff clock: **theta is the dominant force on the back half of the day, and "giving the winner room to breathe" just bleeds the gains back to decay.** The convex winners on BEARISH_REJECTION are caught *faster* (lock 15% off the premium HWM), not by letting them run through a volatile final leg. This triple-confirms lesson **C28** (exit mechanics are locally optimal; once stop-rate is high, *tightening* the lock — not widening it — is the only exit knob with juice) and adds a new lesson candidate: **vol-scaling the trail is anti-edge for 0DTE because the theta clock dominates the vol term.**

## The honest caveats (why this is PROMOTE-**CANDIDATE**, not "ship")

This clears the *stated* gate (real-fills exp ↑ AND anchor-no-regression AND DSR-not-worse), but three independent limits keep it short of ratification:

1. **Anchor coverage is `anchor_fills = 1`** (only 4/29 grades on real fills for this population; 5/01 doesn't fill at the proxy levels and 5/04 — J's biggest winner — has **zero** option bars in the cache). The anchor-no-regression leg passes *trivially*: every variant scores the identical $67.2 (ATM) / $98.7 (ITM2) on 4/29 because that trade hits TP1 + a clean exit before any trail width binds. So "no-regression" is necessary-not-sufficient (C24), not strong evidence the tighter trail protects J's convex winners. **This is the single biggest reason not to wire it yet.**
2. **DSR is WEAK, not PASS.** Even the winner sits at DSR 0.34 (ATM) / 0.105 (ITM2), PSR 0.85 / 0.58. ITM2 PSR 0.58 is barely above a coin flip — the ITM2 population is near-zero-Sharpe and the sign-flip to +$574 is fragile.
3. **Proxy levels + single window.** Levels are historically-rebuilt ★★ proxies, not production ★★★ named levels, and this is a single in-sample window with **no OOS/WF split** (the harness does a same-population A/B, not a walk-forward). Absolute P&L is a proxy; the *ranking* (tight > wide) is the trustworthy part because it's internally consistent across variants.

## A/B numbers — real-fills (OPRA), production premium chandelier as baseline

**Baseline = v15 production chandelier:** `mode=trailing, threshold +5%, stop_offset +10%, trail 20%` off premium HWM. (Note: with the *chandelier* as baseline, ATM is +$1,072 — vs the prior chart-stop-only timecond baseline of −$5,958. The chandelier is doing real work; this sweep asks only whether its *trail rule* can be improved.)

### PRIMARY: BEARISH_REJECTION_MORNING (the confirmed setup) — n_signals 175

| Strike | Variant | Total P&L | Δ vs base | Exp | WR | Anchor EC | DSR | Gate |
|---|---|--:|--:|--:|--:|--:|--:|---|
| ATM | **Baseline trail-20%** | **+$1,071.7** | — | +$7.94 | 79.3% | +$67.2 | 0.168 | — |
| ATM | **fixed_premium_15** | **+$2,430.4** | **+$1,358.8** | +$18.00 | 79.3% | +$67.2 | 0.343 | **PROMOTE-CANDIDATE** |
| ATM | **underlying_fixed_0.30%** | **+$2,426.3** | **+$1,354.6** | +$17.97 | 76.3% | +$67.2 | 0.309 | **PROMOTE-CANDIDATE** |
| ATM | regime_premium_GENTLE | +$843.3 | −$228.4 | +$6.25 | 79.3% | +$67.2 | 0.144 | NOT-BETTER |
| ATM | fixed_premium_25 | +$715.5 | −$356.2 | +$5.30 | 79.3% | +$67.2 | 0.130 | NOT-BETTER |
| ATM | fixed_premium_30 | +$532.6 | −$539.1 | +$3.95 | 79.3% | +$67.2 | 0.113 | NOT-BETTER |
| ATM | underlying_regime | +$474.9 | −$596.8 | +$3.52 | 79.3% | +$67.2 | 0.107 | NOT-BETTER |
| ATM | regime_premium_WIDE_HIVOL | +$467.0 | −$604.8 | +$3.46 | 79.3% | +$67.2 | 0.108 | NOT-BETTER |
| ATM | underlying_fixed_0.50% | +$445.5 | −$626.2 | +$3.30 | 79.3% | +$67.2 | 0.105 | NOT-BETTER |
| ITM2 | **Baseline trail-20%** | **−$601.2** | — | −$4.89 | 77.2% | +$98.7 | 0.046 | — |
| ITM2 | **fixed_premium_15** | **+$574.4** | **+$1,175.6** | +$4.67 | 77.2% | +$98.7 | 0.105 | **PROMOTE-CANDIDATE** |
| ITM2 | **underlying_fixed_0.30%** | **+$197.4** | **+$798.6** | +$1.60 | 74.0% | +$98.7 | 0.082 | **PROMOTE-CANDIDATE** |
| ITM2 | regime_premium_GENTLE | −$790.9 | −$189.7 | −$6.43 | 77.2% | +$98.7 | 0.039 | NOT-BETTER |
| ITM2 | regime_premium_WIDE_HIVOL | −$1,090.2 | −$489.0 | −$8.86 | 77.2% | +$98.7 | 0.030 | NOT-BETTER |
| ITM2 | fixed_premium_25 | −$1,138.4 | −$537.2 | −$9.25 | 77.2% | +$98.7 | 0.029 | NOT-BETTER |
| ITM2 | fixed_premium_30 | −$1,262.0 | −$660.8 | −$10.26 | 77.2% | +$98.7 | 0.026 | NOT-BETTER |
| ITM2 | underlying_fixed_0.50% | −$2,265.9 | −$1,664.7 | −$18.42 | 76.4% | +$98.7 | 0.009 | NOT-BETTER |
| ITM2 | underlying_regime | −$2,495.4 | −$1,894.2 | −$20.29 | 76.4% | +$98.7 | 0.006 | NOT-BETTER |

**Monotone gradient (the load-bearing read):** tighter trail → higher P&L, on both strikes, with zero exceptions. 15% > 20% > 25% > 30% in total P&L; the regime maps and the wide underlying trails all land in the loss region. The signal is not noise — it's a clean ordering across 8 variants × 2 strikes.

## Is a regime-conditional chandelier worth proposing? — NO

- **The fixed 20% is NOT what to keep, but a regime-conditional trail is the wrong fix.** The data says move *tighter* (a fixed ~15% premium trail), not vol-scaled. Adding VIX-conditioning strictly hurt in every cell tested. Proposing a regime chandelier on this evidence would be manufacturing a story the numbers reject.
- **What IS worth a (separate, future) proposal:** tighten the v15 premium chandelier trail from 20% → ~15% — but ONLY after (a) an OOS/WF split confirms the IS edge holds out-of-sample, (b) a production-★★★-level replay (not proxy levels) reproduces the ranking, and (c) the anchor-no-regression leg is re-checked once 5/01 + 5/04 have gradeable option bars (today they don't, so the convex-winner-protection claim is untested). That is a chandelier-*tightening* candidate, not a regime candidate, and it is out of scope for this propose-only run.

## What was tested / changed

- **Added** (opt-in, default OFF → zero production impact) to `simulate_trade_real`:
  - `profit_lock_trail_basis` ∈ {`premium` (v15 default), `underlying`} — `underlying` trails the SPY move (put: session low) per the research; a separate all-units profit-lock exit sharing the same +5% arming gate.
  - `profit_lock_trail_pct_by_vix` / `profit_lock_trail_underlying_pct_by_vix` — `{vix_ceiling: trail}` regime maps resolved against `entry_vix` (first ceiling ≥ entry-VIX wins; falls through to the scalar when VIX unknown / above all ceilings).
  - `profit_lock_trail_underlying_pct`, `entry_vix`.
- **Verified default-off path is byte-for-byte identical:** new `backtest/tests/test_chandelier_regime.py` (6 tests — default==explicit-v15-chandelier, regime map widens vs tight scalar, VIX-unknown==scalar, underlying trail fires on SPY rally, underlying default-off, resolver buckets) + the full real-fills suite (78 passed incl. 7 e2e anchor-reproduction + 59 graduated guards). Gym `--skip-replay` green (87/87).
- **No** params / heartbeat / doctrine changed. Watchers/setups untouched.

## OP-20 disclosures

- **Authority:** real-fills (`lib.simulator_real` + OPRA cache, valid through 2026-05-29). BS-sim / SPY-space grade NOT used.
- **Anchor coverage is THIN:** `anchor_fills = 1` (only 4/29); 5/04 (+$730) has zero cached option bars; the trail change is invisible to 4/29 (TP1+clean exit). Anchor-no-regression is necessary-not-sufficient (C24).
- **Levels:** historically-rebuilt ★★ proxies (`_detect_from_history` as-of each day), NOT production ★★★ named levels. Absolute P&L is a proxy; the variant *ranking* is internally consistent and is the trustworthy output.
- **Regime key:** `entry_VIX` = as-of VIX at the firing bar from `_align_vix_to_spy` (no look-ahead).
- **No OOS/WF split** in this harness — it is a same-population same-window A/B across exit configs. Walk-forward + production-level replay are required before any ratification.
- **DSR:** per-trade dollar P&L (constant qty=3 notional), PBO skipped (no CSCV matrix), n_trials=8 (grid size). Advisory only; even the winner is WEAK (not PASS).
