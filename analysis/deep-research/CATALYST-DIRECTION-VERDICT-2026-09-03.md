# CATALYST → DIRECTION — VERDICT: **FAIL. Stop the line.** (2026-09-03)

> Run exactly as frozen in `analysis/recommendations/prereg-catalyst-direction-2026-09-03.json`
> (committed `a0768dde`, **before** the harness existed — `git log` proves the order).
> Harness: `backtest/tools/catalyst_direction_null_harness.py`.
> Raw: `analysis/multi-lane/catalyst-direction-stageA.json`.

---

## THE RESULT

**7,019 signals across 9 symbols over 12 months. News does not predict direction. It fails
the random-entry null at every horizon.**

| Horizon | signed return | hit rate | Holm p | null MAX | gate |
|---|---:|---:|---:|---:|---|
| +10 min | +0.0002% | 49.94% | 0.483 | 0.00555 | **FAILS** |
| **+30 min** *(headline)* | −0.00065% | 49.61% | 0.592 | 0.01157 | **FAILS** |
| +60 min | +0.00153% | 49.58% | 0.453 | 0.01888 | **FAILS** |

Block-bootstrap 95% CI by `(symbol, trading_day)` block, 1,401 blocks × 2,000 resamples —
**straddles zero at every horizon**: +10min [−0.0053, +0.0057], +30min [−0.0106, +0.0093],
+60min [−0.0123, +0.0158].

Per symbol at 30 minutes — **4 of 9 sign-matching**, and the spread is noise-shaped:

| | AAPL | MSFT | AMD | GLD | QQQ | SPY | NVDA | TSLA | IWM |
|---|---|---|---|---|---|---|---|---|---|
| n | 539 | 683 | 222 | 87 | 72 | 3,897 | 960 | 550 | 9 |
| mean | +0.033% | +0.014% | +0.014% | +0.006% | +0.006% | −0.004% | −0.012% | −0.014% | — |
| hit | 51.2% | 49.2% | 50.9% | 49.4% | 47.2% | 49.8% | 47.3% | 50.9% | *n<50* |

**Sample size is not the problem.** 7,019 signals is 140× the pre-registered minimum of 50,
across a full 12 months (2025-09-02 → 2026-08-31), on **SIP** bars, with **0.00% fetch errors
on all 9 symbols** (788 paginated requests). This is a clean, well-powered negative.

**Concentration is not the problem either.** SPY carries 55.5% of the signals; excluding it
entirely still fails the null MAX.

---

## The finding that outranks the null

**This is the THIRD independent confirmation, now on a completely different information
class, that this rig detects WHEN something will move and never WHICH WAY.**

| | Weekly lane (08-18) | Multi lane (08-20) | **Catalysts (09-03)** |
|---|---|---|---|
| Information class | price geometry | price geometry | **news** |
| Trigger | 1H level interaction | 5-min level + structure | **Benzinga headline** |
| Evidence | 684 real positions | 7,489 signals | **7,019 signals** |
| Hit rate | 49.9–51.4% | 49.1–49.4% | **49.6–49.9%** |
| Signed vs null | fails | fails | **fails** |
| Abs-move | ~0 pooled | +7.6 to +12.6% | **+4.7 to +5.7%** |

The first two could be dismissed as one detector failing. **A news headline shares no
machinery, no timebase and no mathematics with a level-rejection trigger — and returns the
same 49%.** Whatever is missing is not in the detector.

---

## The correction that matters more than the null

Stage A (2026-08-20) reported an abs-move lift of **+7.63 / +12.54 / +12.59%** and it was
never null-tested — `multi_intraday_null_harness.py` applies `random_null()` to signed
returns only, and the abs lift was a bare point estimate against an **unconditional pooled
baseline**. This prereg named that defect in advance and fixed it: abs-move here is drawn
against the **same matched random-entry null**, same counts, same draws.

Properly tested, the volatility lift is:

| Horizon | observed abs | null MAX | lift | 95% CI | CI clears null MAX? |
|---|---:|---:|---:|---|---|
| +10 min | 0.13302% | 0.12705 | **+4.70%** | [0.1252, 0.1418] | **no** |
| +30 min | 0.22556% | 0.21348 | **+5.66%** | [0.2122, 0.2402] | **no** |
| +60 min | 0.31089% | 0.29471 | **+5.49%** | [0.2905, 0.3328] | **no** |

Two things follow, and both matter:

1. **The volatility signal is real for the first time** — it beats a properly-constructed
   null at all three horizons, which the Stage-A number never did.
2. **It is roughly half the size it looked, and it is not clean.** At the headline horizon
   +5.66%, not +12.54%; and at every horizon the block-bootstrap CI's lower bound sits
   *below* the null MAX. Consistent and positive, but marginal.

Anyone who had built on Stage A's +12.54% would have been sizing against a number that a
matched null cuts in half.

---

## What the frozen decision rule authorizes

The prereg pre-committed this outcome by name:

> *"If abs-move lift is significant while signed return is not, the signal is a volatility
> detector… that is NOT a pass — this shop trades long directional premium only. Recorded as
> a finding, never acted on."*

- **The catalyst line STOPS.** Verdict written; machinery retained.
- **No sentiment classifier swap. No threshold sweep. No more names. No re-slice.** All four
  are on this prereg's kill-list as dead-knobs dressed as progress.
- Specifically: `earnings` (n=117, +0.095%, 51.3%) is the largest per-class number and is
  **descriptive only** — per-class results are excluded from the corrected family, and
  chasing it is the exact re-slice the kill-list forbids.

---

## Two instrument notes worth keeping

- **The session-boundary guard was load-bearing, not defensive decoration.** RTH-only
  filtering makes different trading days *adjacent in array index* though hours apart in
  wall-clock. Without an explicit same-day check, a late-session headline's forward window
  splices into the next morning and reports an overnight gap as a "60-minute reaction." It
  fired 62 times on NVDA, 55 on TSLA, 33 on AAPL. Those would have been fabricated moves.
- **The ≤3-symbol specificity filter did most of the work.** NVDA: 5,755 raw articles →
  3,099 dropped as market-wraps tagging >3 symbols. Without it the study would have measured
  the market and called it a name-specific catalyst.

---

## Honest read for the next session

Two information classes. Three well-powered tests. One answer.

**The expansion beyond SPY is not a signal story.** Nothing in this repo's detector family —
price geometry or news — carries directional information off SPY at intraday horizons. The
only thing that survives contact with a null is a **volatility** read, now measured properly
at ~+5%, which the playbook has no way to express (one direction at a time, long premium
only). Making it expressible means two-sided structures, which is a strategy-class change and
J's call, not this line's.

What remains genuinely open, and is *not* answered here:
- The production filter stack has still never been replayed bar-by-bar on any symbol,
  including SPY. The 58.23% live number and the 49% replayed numbers have never been compared
  under one method.
- The 0DTE instrument itself is real and liquid — `analysis/multi-lane/universe-screen-0dte-2026-09-04.json`,
  6 of 9 Mon/Wed/Fri single names inside the lane's own spread and cost rules. **A tradeable
  instrument with no validated signal is not an opportunity.**

Per OP-22, a closing verdict is a valid terminal state. This is one.
