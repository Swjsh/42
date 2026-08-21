# WP-4 STAGE A — VERDICT: **FAIL. Stop the lane.** (2026-08-20)

> Run exactly as frozen in `analysis/recommendations/prereg-multi-intraday-null-2026-08-20.json`
> (frozen before the harness ran once). Harness:
> `backtest/tools/multi_intraday_null_harness.py`. Raw:
> `analysis/multi-lane/intraday-null-stageA.json`.

---

## THE RESULT

**7,489 signals across 9 symbols. The signal does not predict direction. It fails the
random-entry null at every horizon.**

| Horizon | signed return | hit rate | abs-move lift | null MAX | gate |
|---|---|---|---|---|---|
| +10 min | −0.0041% | 49.06% | **+7.6%** | 0.0087 | **FAILS** |
| **+30 min** *(headline)* | −0.0022% | 49.35% | **+12.5%** | 0.0126 | **FAILS** |
| +60 min | −0.0073% | 49.17% | **+12.6%** | 0.0230 | **FAILS** |

Per symbol at 30 minutes — **2 of 9 positive**, and the spread is noise-shaped:

| | TSLA | MSFT | IWM | QQQ | SPY | AAPL | NVDA | GLD | AMD |
|---|---|---|---|---|---|---|---|---|---|
| mean | +0.055% | +0.026% | −0.002% | −0.003% | −0.007% | −0.012% | −0.015% | −0.019% | −0.051% |
| hit | 51.6% | 48.0% | 50.8% | 50.2% | 49.8% | 46.3% | 48.8% | 46.8% | 50.6% |

**Sample size is not the problem.** 7,489 signals is 149× the pre-registered minimum of 50 —
WP-1's 5-minute timebase delivered signal density in abundance. This is a clean, well-powered
negative.

## What it IS detecting — and why that is still a FAIL

Absolute-move lift is **positive and consistent** (+7.6% / +12.5% / +12.6%) while signed return
sits at zero and hit rate sits at ~49% across every symbol. **The trigger marks "something is
about to move" without saying which way.**

The pre-registration named this outcome in advance and pre-committed to rejecting it:

> *"If absolute-move lift is significant while signed return is not, the signal is a volatility
> detector. That is NOT a pass — this lane trades long directional premium only."*

A direction-blind signal expressed as long directional premium must lose the spread and the
theta every time. That is arithmetic, not opinion.

## The finding that makes this bigger than one lane

**This is the second independent confirmation, on a completely different timeframe and hold
model, that the level-interaction + structure-shift signal family carries no directional
information.**

| | Weekly lane (2026-08-18) | Multi lane (2026-08-20) |
|---|---|---|
| Timeframe | 1H trigger / daily zones | **5-minute** trigger |
| Hold model | multi-day | **intraday** |
| Context | partial | **full parity** — VIX, HTF-15m, level-state memory |
| Symbols | 9 | 9 |
| Signals | 463 | **7,489** |
| Hit rate | 49.9–51.4% | **49.1–49.4%** |
| Abs-move lift | ~0 pooled | **+7.6 to +12.6%** |
| Verdict | fails null | **fails null** |

The weekly run could be dismissed as a timeframe artifact — that was the leading hypothesis, and
it was tested and refuted. This run removes the remaining excuses: **the finest timebase the
production engine uses, full context parity, 149× the required sample, nine symbols.** Same
answer.

**And note what was NOT tested here: the SPY engine on SPY.** SPY is in this sample and scores
−0.007% at 49.8% — but this is the FORKED scoring on 5-minute bars with lane-computed levels,
not the production engine with its curated `key-levels.json`, trendlines and multi-day level
memory. This result says *this transplant does not carry direction on these names*; it does not
adjudicate the production SPY engine, whose own recent evidence (three green sessions, +$1,128)
stands on its own ledger. Conflating the two would be exactly the evidence-blending the
workpackage kill-list forbids.

## What the frozen decision rule authorizes

- **WP-5 (paper orders) does NOT proceed.** It was absolutely gated on a Stage-A pass.
- **Stage B (option-level walk) does NOT run.** Its only purpose was to add expression realism
  to a signal that has an edge; there is nothing to express.
- **No threshold sweep. No "try more names." No re-slice.** All three are on the kill-list as
  dead-knobs dressed as progress, and the prereg pre-committed that a null STOPS the lane.

## What survives, and is worth keeping

The machinery, and it is not small:

- A faithful symbol-generic fork of the SPY scoring engine (scale-invariance proven at $40 and
  $700), never importing or touching the original.
- 5-minute two-tier batch pipeline at ~2.4 req/min against a 200/min limit.
- Context parity: real VIX + MAs, HTF-15m, persistent per-symbol level-state memory.
- Named-blocker diagnosis + nightly histogram — "why didn't it trade" is now one read.
- A no-look-ahead intraday replay harness with a random-entry null, reusable for **any** future
  signal on **any** symbol set. This is the asset. The next idea gets adjudicated in one session.
- Crypto-safe shared-account handling, AST-guarded no-order-path, 300+ RED-proofed tests.

**The lane is stopped. The instrument that stopped it is the thing worth having.**

## Honest limitations of this verdict

- Stage A measures the SIGNAL on the UNDERLYING. It does not price spread/theta — but that only
  makes the real result *worse*, never better, so it cannot rescue a fail.
- 5-minute history depth is finite (~6,000 bars/symbol here, ~8,000 available); a longer window
  is possible but would not plausibly reverse a 7,489-signal, 9-symbol, all-horizons result.
- The abs-move lift is descriptive, not a validated volatility edge. The weekly lane's own
  cautionary tale is that a lift like this collapsed under a wider symbol sample — here it holds
  across 9, which makes it *interesting*, not *actionable*. Any attempt to trade it needs its own
  pre-registration, its own non-directional structure, and its own null gate. **It is not a
  consolation prize and must not be treated as one.**
