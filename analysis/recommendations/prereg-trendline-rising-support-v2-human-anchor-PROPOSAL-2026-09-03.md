# PRE-REGISTRATION (PROPOSAL, NOT ARMED) — rising-support human-anchor mode, 2026-09-03

> ⛔ **SUPERSEDED (2026-09-03, same evening).** This proposal was never armed and never
> built an instrument. It is superseded by the frozen, built, scheduled version:
> [`prereg-trendline-rising-support-human-anchor-2026-09-03.md`](prereg-trendline-rising-support-human-anchor-2026-09-03.md)
> (`setup/scripts/trendline_human_anchor_shadow.py` + `Gamma_TrendlineHumanAnchorShadow`).
> That file freezes the anchor rule this one only sketched (A = running session-low, B =
> first confirmed higher swing low, no third-touch gate), backfills once over every cached
> session, and gates any verdict to forward-only data after 2026-10-30. Left in place
> per append-only history — read the superseding file, not this one, for the live rule.

**Status: proposal only.** This file registers a hypothesis and a measurement plan for a
FUTURE forward or historical-population study. It does not arm anything, does not modify
`backtest/lib/trendline_detector.py`, and is not itself evidence of an edge — the finding
motivating it is n=1 session. No accrual clock starts until a follow-up session builds the
instrument described in §3 and commits it alongside a dated addendum to this file, per the
freeze convention used by `prereg-trendline-tight-exit-shadow-2026-09-03.md`.

Source: [`trendline-today-exhibit.md`](../deep-research/2026-09-03-money/trendline-today-exhibit.md)
/ `.json` (same directory) — mechanical, read-only reproduction of J's 2026-09-03 rising
support line (08:20→10:10 5m / 08:15→10:00 15m), run against `backtest/lib/
trendline_detector.py` with its own default rules.

## 1. What today's exhibit showed (facts, not yet a study)

- The repo's pivot-anchored detector (`detect_trendlines`, default `min_touches=3`,
  `pivot_window=2`, strict fractal-neighbor pivot test) could not construct J's specific
  rising support line at 10:55 ET with no look-ahead, on either 5m or 15m, with or without
  premarket bars — and on 15m, J's literal anchor (`08:15` wick) is **never** a confirmed
  swing-low pivot in this session, even with full-day hindsight (`06:45`/`07:30` are lower
  and dominate the same fractal neighborhood).
- A one-bar-adjusted version of the 5m line (anchored at the *actual* nearest pivot, `08:15`
  instead of `08:20` — one cent lower) DOES eventually clear the 3-touch minimum, at 14:40 —
  close to J's own "broke at 14:30" call — but immediately racks up 17 straight close
  violations from 14:55 onward (fit score −79.7). Never a line the detector's own ranking
  would surface.
- The CLOSE-based read (line reclaimed and held through 10:55, broken by close at/near
  14:30) is directionally right, especially on the 15m all-wick variant, which breaks by
  close on the exact 14:30 bar.
- This reproduces, with an exact bar and an exact gate, the existing memory-doctrine finding
  "trendline shadow lane (2026-08-20): pivot-highs only; rising support invisible" — and
  localizes the cause to the **3-touch minimum + strict fractal-pivot anchor test**, not to
  the rising-slope constraint (`require_slope='rising'` already exists and works as
  documented) and not to premarket exclusion alone (premarket bars were included in every
  failing configuration above).

## 2. The hypothesis this motivates (UNTESTED beyond n=1)

A **2-point, human/close-anchored rising support line** (anchor mode: nearest local
low-before-reversal on each side of a visible dip, NOT gated by the 3-touch fractal-pivot
test) that is subsequently judged by (a) whether price closes back above it within N bars of
the second anchor, and (b) how long it holds before a close-break, may carry information the
current pivot-gated detector systematically discards — specifically on setups where a human
chart-reader identifies a "held then broken" shape from only 2 legible extremes, which is
exactly the shape the 3-touch gate is built to reject as noise.

This is **not** a claim that 2-touch lines are profitable — the null (this is exactly the
"one reaction masquerading as a trend" case `min_bars_between_touches`/`min_touches` exist to
filter, per the detector's own docstring citing the Tori method) is the prior. The point of a
forward study is to find out, not to assume either way.

## 3. Measurement plan (to be built before any accrual clock starts)

- **Instrument (not yet built):** a shadow-only variant of `detect_trendlines` (or a
  standalone function reusing its `_fit_candidate` machinery) with `min_touches` lowered to 2
  for `kind="support"`, `require_slope="rising"` only — run in parallel with the existing
  `trendline_shadow.py` lane, never replacing it, never touching `filters.py`'s live bear
  trigger or the shadow-only bull reclaim trigger.
- **Population:** every RTH session going forward from the build date (forward-only, per the
  contamination argument in the tight-exit-shadow prereg — a retrospective population here
  would let this exact exhibit's known outcome leak into the population it's judged against).
- **Primary measurement:** for every 2-touch rising-support candidate the relaxed detector
  finds, log (i) whether price closes back above it within the next N bars of the second
  anchor being confirmed, (ii) bars-to-break (close < line − $0.20), (iii) subsequent 60-min
  high after the reclaim and subsequent 60-min low after the break — the same four numbers
  this exhibit computed by hand.
- **Gate before any ratification:** same standard as every other shadow lane in this repo
  (OP-11 §16 doctrine) — session-clustered bootstrap CI, n≥15 evidence, no cherry-picked
  single-day story. Today's n=1 exhibit is the MOTIVATION for building the instrument, never
  the evidence for shipping it.

## 4. Explicit non-goals

- Not a change to `min_touches`, `pivot_window`, or any other default in
  `backtest/lib/trendline_detector.py` — those defaults are cited-precedent (Tori method,
  `filters.py` convergence) and stay as-is for every existing consumer.
- Not a live or paper trading trigger of any kind. Shadow-only, log-only, per the
  trendline-shadow-lane convention already running (`Gamma_TrendlineShadow`).
- Not a claim about J's 08:20/08:15 anchors being "wrong" — his read is a legitimate
  chart-reading judgment call ("body to wick from candle to candle but close enough"); this
  proposal is about whether the ENGINE should also be able to see lines built the way a human
  eye builds them, not about correcting J.
