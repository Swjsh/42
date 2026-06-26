# H6 — Reversal-Off-Session-Extreme

**Rank:** 6 of 8 · **Score:** 6.0 · **Seam:** J winner archetype (under-built) · **Status:** PROPOSAL (test, do not ship)

---

## The setup / signal

A distinct **fade-the-exhaustion** detector, separate from RIDE_THE_RIBBON trend-following:

- Price pushes to a fresh session high (or low) that is **stretched far from VWAP** (`dist_to_vwap >= X` ATRs), prints an exhaustion bar (long wick rejecting the extreme, declining volume vs the prior push), then a confirming reversal bar → **put** (fade the high) / **call** (fade the low).
- Stop = the exact session extreme + buffer (mechanical, tight). Target = back toward VWAP / first named level.

This is the "reversal off session high/low" archetype the J-winner study isolated as one of *two* distinct repeatable plays — and it's the one the engine builds least.

## The insight (why it should have edge)

From `J-WEBULL-EDGE` archetype tally: "trend-continuation 3 · **reversal-off-extreme 2** · momentum-breakout 2 · pullback-resumption 2," and:

> "Two distinct, repeatable plays: (1) trend-continuation/pullback-resumption with VWAP, and (2) **reversal off a session high/low** (the fade puts)." The 2 reversal winners (3/14 SPXW 4195P +$500, 5/12 SPXW 3810P +$390) "deliberately faded price that had pushed *above* VWAP into a session high — catching the top."

Both reversal winners were **1-lot, clean, held minutes** — exactly J's profitable profile. The engine's BEARISH_REJECTION is *level*-anchored (fade a named resistance); this is *extreme*-anchored (fade a fresh session high regardless of a named level), a genuinely different trigger. It also pairs naturally with H1's role-aware VWAP gate (the reversal arm). The `close_ceiling_fade_watcher.py` and `bearish_reversal_at_level_watcher.py` are adjacent but not this exact "fresh-extreme stretched-from-VWAP exhaustion" trigger.

## EXACT backtest to validate

1. **Build the detector** (TDD per L03 — hand-compute the 3/14 and 5/12 SPY-proxy bars first; SPX/SPY ~10:1): fresh-session-extreme + dist-from-VWAP threshold + exhaustion-wick + volume-decline + reversal-bar confirm. Look-ahead-free (extreme confirmed only on closed bars; C6).
2. **Anti-noise check (C27 / L145):** measure firing rate — a fade detector that fires >40% of days is reading noise. Restrict to genuine stretched extremes.
3. **Grid:** dist-from-VWAP {1.0,1.5,2.0 ATR} x wick-ratio {0.5,0.6} x vol-decline {on,off} x strike/stop poles.
4. **Data/OOS/real-fills/anchor:** standard contract. NOTE — the OP-16 anchors are trend-rejection puts, not extreme-fades, so this detector should be a **no-op on the anchors** (`edge_capture` unchanged); its edge is *additive* (new trades on new days), validated on its OWN population WR, not via anchor capture.
5. **Guards:** L171 truncation, **L172 null-MAX is critical** (fades are the classic exit-structure-artifact trap — a tight stop + runner on random fades can look positive), C24 (the 2 J reversal winners are anchor *context*; verify the IS *population* of fades is profitable, not just the 2 examples).
6. **Scorecard:** `analysis/recommendations/h6-reversal-off-extreme.json` with population WR, firing rate, null_pass, and the 3/14//5/12 reconstruction.

## Kill criteria (reject if ANY)

- Population WR < 50% or per-trade fails the null MAX (L172) → fades are exit-structure, not signal (the single highest-probability failure for any reversal idea).
- Firing rate > ~40% of days (C27 — measuring noise).
- Real-fills expectancy negative while SPY-space positive (C3 — direction edge that doesn't survive the option transform).
- The 2 J reversal winners are the *only* profitable instances (C24 — anchor-only, no population edge).

## Expected edge_capture x feasibility

**edge_capture MED-HIGH** (a whole second repeatable J play the engine barely builds; additive, doesn't threaten anchors). **feasibility MED** (new detector + high null/noise risk — fades are where fake edges hide). Ranked #6 because the failure-probability is genuinely elevated (most mean-reversion 0DTE ideas die at the null gate — see L171 IBS, L172 RSI2), but the upside (a validated second archetype) is large.

## Disclosure (OP-20)

Highest fake-edge risk in the shortlist — the L171/L172 guards exist precisely for ideas like this. Disclose null-baseline numbers prominently. C24: do not extrapolate from the 2 anchor winners; the population verdict governs.
