# Time-Conditional Exit Sweep — Game Plan 2 (theta-cliff exit refinement)

**Date:** 2026-06-19 · **Window:** 2025-01-01 .. 2026-05-29 (OPRA real-fills) · **Status:** RESEARCH / propose-only (Rule 9)
**Scorecard JSON:** [`timecond-exit-sweep.json`](timecond-exit-sweep.json) · **Harness:** `backtest/autoresearch/sweep_timecond_exit.py`
**Knob added (opt-in, default OFF):** `lib.simulator_real.simulate_trade_real(early_cutoff_et, early_cutoff_min_favor_pct)`

## Verdict (headline)

**15:50 is already right. An earlier time-conditional exit is NOT worth shipping on this evidence. `any_promote_candidate = False`.**

The finding (back-loaded 0DTE theta, sharp cliff ~15:30) is real, and the data confirms its *direction* — pulling stagnant positions at **15:00** saves the most premium. But it does not clear the promotion bar, for three independent reasons:

1. **For the CONFIRMED setup (BEARISH_REJECTION_MORNING) the cutoff is a no-op.** 128 of 135 graded trades (95%) already exit *before* 15:00 — via ribbon-flip (75), level-stop (49), or TP1+runner — because the setup fires 09:35–10:55 ET and resolves by midday. Only 7 trades ever reach a 15:00 cutoff. Delta P&L vs the 15:50 baseline = **$0.00** at every cutoff/threshold. There is no late-day theta to step off, because the confirmed edge isn't holding into the close.
2. **For the BROAD bearish-continuation book the cutoff reduces the bleed but cannot create an edge.** The whole population is real-fills-negative under chart-stop-only (PSR ≈ 0 → DSR **FAIL** on the baseline itself), matching the prior `bearish-continuation-family.json` result. Cutting at 15:00 trims the loss (ATM −$3,266 → −$2,750, +$516; ITM2 −$12,830 → −$11,455, +$1,375) but the result is still deeply negative — so DSR/PSR correctly refuses to bless it. You can't make a losing population promotable by shaving its tail.
3. **Earlier cutoffs REGRESS J's anchor winners** (the exact "don't clip the convex winners" risk). On the broad book, 15:15 and 15:30 cutoffs cut anchor-day edge_capture sharply (ATM 15:30 → −$91.8; ITM2 15:30 → −$225.3 vs baseline +$14.7) because they catch J's anchor-day positions that were still developing into the afternoon.

This is a **clean, valuable no-win**: it tells us where NOT to spend effort, and it triple-confirms lesson **C28** (*ribbon flip is a lagging exit; exit mechanics are locally optimal; focus research on ENTRIES — exit tuning has diminishing returns once stop-rate > 70%*).

## A/B numbers — real-fills (OPRA), chart-stop only

### PRIMARY: BEARISH_REJECTION_MORNING (the confirmed setup) — n_signals 175

| Strike | Variant | Total P&L | Exp | WR | n | Anchor edge_capture | DSR |
|---|---|--:|--:|--:|--:|--:|---|
| ATM | **Baseline 15:50** | **−$5,957.8** | −$44.13 | 62.2% | 135 | +$67.2 | FAIL |
| ATM | Best (15:00 / +0%) | −$5,957.8 | −$44.13 | 62.2% | 135 | +$67.2 | FAIL |
| ITM2 | **Baseline 15:50** | **−$14,240.3** | −$115.77 | 56.9% | 123 | +$98.7 | FAIL |
| ITM2 | Best (15:00 / +0%) | −$14,240.3 | −$115.77 | 56.9% | 123 | +$98.7 | FAIL |

Δ P&L vs baseline = **$0.00** for every variant (trades resolve before the cutoff). avg win ≈ +$119 / avg loss ≈ −$313–$416 → the loss tail (not late theta) is what's hurting; an earlier time stop doesn't touch it.

### BROAD: pooled BRM + LEVEL_BREAK_FIRST_STRIKE + HEAD_AND_SHOULDERS_BEAR — n_signals 203

| Strike | Variant | Total P&L | Δ vs base | Exp | WR | Anchor edge | Gate verdict | DSR |
|---|---|--:|--:|--:|--:|--:|---|---|
| ATM | **Baseline 15:50** | **−$3,265.8** | — | −$20.04 | 62.6% | −$58.8 | — | FAIL |
| ATM | 15:00 / +0% (best $) | −$2,749.8 | **+$516.0** | −$16.87 | 62.6% | −$1.8 | BETTER-BUT-DSR-FAIL | FAIL |
| ATM | 15:15 / +0% | −$2,830.8 | +$435.0 | −$17.37 | 62.6% | −$82.8 | BETTER-BUT-ANCHOR-REGRESSION | FAIL |
| ATM | 15:30 / +0% | −$3,016.8 | +$249.0 | −$18.51 | 62.6% | −$91.8 | BETTER-BUT-ANCHOR-REGRESSION | FAIL |
| ITM2 | **Baseline 15:50** | **−$12,830.2** | — | −$83.86 | 56.9% | +$14.7 | — | FAIL |
| ITM2 | 15:00 / +25% (best $) | −$11,455.3 | **+$1,374.9** | −$74.87 | 56.9% | +$11.7 | BETTER-BUT-ANCHOR-REGRESSION | FAIL |
| ITM2 | 15:15 / +10% | −$11,893.3 | +$936.9 | −$77.73 | 56.9% | −$192.3 | BETTER-BUT-ANCHOR-REGRESSION | FAIL |
| ITM2 | 15:30 / +10% | −$12,050.2 | +$780.0 | −$78.76 | 56.9% | −$225.3 | BETTER-BUT-ANCHOR-REGRESSION | FAIL |

**Gradient reading:** earlier cutoff → bigger P&L improvement (15:00 > 15:15 > 15:30), exactly as the back-loaded-theta finding predicts. The favor threshold has a small effect (a slightly higher threshold cuts a few more stagnant ITM2 positions and *helps* the anchor edge marginally at 15:00). But every cell stays negative and either fails DSR (negative population) or regresses anchors. No cell is a clean PROMOTE.

## Why DSR FAILs everywhere (not a harness bug)

DSR/PSR gate on the probability the *true* Sharpe is positive. The baseline real-fills populations have PSR ≈ 0.00–0.19 — i.e. the full-window bearish-continuation book is genuinely negative-expectancy under chart-stop-only (the same C1/C3 "SPY-edge ≠ option-edge" collapse the prior `bearish-continuation-family.json` documented). A time-conditional exit that shrinks a loss from −$12.8k to −$11.5k does not move the series into positive-Sharpe territory, so the gate correctly withholds promotion. **The exit knob is a damage-control lever on a losing population, not an edge-creator.**

## So what IS the leverage? (forward pointer, not a ship)

This run closes the "is 15:50 too late?" question for the confirmed setup: **no.** The afternoon-theta thesis only bites a population that *holds losers into the afternoon* — and the confirmed setup doesn't (it's a morning setup that resolves by midday). The real leverage named by GP2 and the prior scorecard remains **REGIME gating of entries**, not exit timing:
- The broad book is real-fills-negative; trimming its tail ~$0.5–1.4k still leaves it negative. The fix is to *not take* the regime-wrong members of that book (Game Plan 1: morning-sign + dealer-gamma regime tag), not to exit them 50 minutes earlier.
- Keep BEARISH_REJECTION_MORNING on its current 15:50 stop (it never reaches it anyway) and its chart-stop/ribbon exits, which the data shows are doing the work.

## What was tested / changed

- **Added** (opt-in, default OFF → zero production impact): `early_cutoff_et` + `early_cutoff_min_favor_pct` on `simulate_trade_real`. Verified default-off path is byte-for-byte identical (18 e2e real-fills tests pass; 4/29 anchor reproduces $134.4 ATM / $197.4 ITM2 exactly). New unit tests: `backtest/tests/test_timecond_exit.py` (4 tests — non-favored cut, favored rides, default unchanged, `>=` boundary).
- **No** params / heartbeat / doctrine changed. Watchers/setups untouched. Gym green (88/88) before the change.

## OP-20 disclosures

- **Authority:** real-fills (`lib.simulator_real` + OPRA cache, valid through 2026-05-29). BS-sim / SPY-space grade NOT used for the verdict.
- **Anchor coverage is THIN:** 5/04 (J's biggest winner, +$730) has **zero** option bars in the cache → cannot be graded; BRM has an OPRA fill on only 4/29 among the WIN days. The anchor-no-regression gate is necessary-not-sufficient (C24); a tie at n=1 anchor fill is weak evidence (reported, not hidden).
- **Levels:** historically-rebuilt ★★ proxies (`_detect_from_history` as-of each day), NOT production ★★★ named levels (no archive). Absolute WR is a proxy lower-bound; the exit comparison is internally consistent (identical signal population + level set across all variants), so the sign-flip question is answerable.
- **Favor test:** "in favor" = TP1 filled OR current-bar premium ≥ entry×(1+thr), using the current bar **high** (generous — only genuinely stagnant positions get cut), evaluated strictly before the 15:50 stop.
- **DSR:** per-trade dollar P&L (constant qty=3 notional), PBO skipped (no CSCV matrix), n_trials=9 (grid size). Advisory only.
