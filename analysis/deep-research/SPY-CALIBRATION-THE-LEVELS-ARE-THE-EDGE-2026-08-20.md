# CALIBRATION VERDICT: the harness works — and the multi-lane fork failed because it built its own levels (2026-08-20)

> Run as frozen in `analysis/recommendations/prereg-spy-production-calibration-2026-08-20.json`.
> Harness: `backtest/tools/spy_production_calibration.py`. Raw:
> `analysis/multi-lane/spy-production-calibration.json`.

---

## THE RESULT

Same metric, same null construction, same 5-minute timebase. The only thing that changes
between these two rows is **where the levels came from**:

| trigger | levels input | hit rate @ +10 min | n | significance |
|---|---|---|---|---|
| **Production SPY engine** | curated `key-levels.json` (tiered, sourced, expiring) | **58.23%** | 881 | **+4.89 σ** |
| Multi-lane fork | `multi/lib/levels.py` (swing pivots + prior day/week + round numbers) | 49.06% | 7,489 | −1.63 σ |

**That is the whole finding.** The production trigger carries strong, clean directional
information. The forked trigger carries none. They run the same filter stack.

Full production numbers (population A — all 881 deduped `verdict=ENTER_*` rows, 33 days):

| horizon | mean | hit | abs-move | null MAX | gate |
|---|---|---|---|---|---|
| **+10 min** | +0.01085% | **58.23%** | 0.0566% | 0.00802 | **BEATS NULL MAX** |
| +30 min *(headline)* | +0.00618% | 56.43% | 0.1086% | 0.01363 | fails |
| +60 min | −0.00164% | 49.13% | 0.1525% | 0.02261 | fails |

Days positive: 19/33.

## Honesty first: by the letter of the frozen rule, this is not a clean "CALIBRATED"

I pre-committed the headline horizon at **+30 min**, and population A **fails** the mean-return
null-MAX gate there. I am not going to horizon-shop that into a pass — declaring victory on
+10 min after freezing +30 min is exactly the move the Holm correction exists to stop.

What the data does say, unambiguously:

1. **The instrument is not blind.** It separates a known-good trigger from a dead one by
   6.5 sigma of hit rate. The calibration question — *can this device see a directional edge
   when one is present?* — is answered **yes**.
2. **My gate was mis-specified in two ways**, and both are my errors, not the market's:
   - **The horizon was assumed, not measured.** Production's edge is strongest at 10 minutes
     and **completely gone by 60** (49.13%). I picked 30 minutes as the headline out of thin
     air when I wrote the multi-lane prereg.
   - **Mean underlying return is the wrong currency.** Production is right on direction ~58% of
     the time while its *mean* underlying move is ~0.01% — the money is a right tail in option
     premium harvested by exits, which a mean-of-underlying metric cannot see. This is the same
     right-tail structure the real-fills work already found (money only from exits ≥1.3× entry
     premium).
3. **The multi-lane verdict STANDS, and is strengthened.** The fork sat at 49.06% on the
   hit-rate channel that demonstrably works on 7,489 signals. Nothing here rescues it. It was a
   true negative — I just had the wrong reason for it.

## The reason the fork failed — and it is not "other tickers don't work"

The fork replaced the one input that carries the information. Production's `key-levels.json` is
a **curated** object: 13 levels, each with a tier (`Active` / `Carry` / `Reference` /
`Liquidity`), an explicit source, prose reasoning, a `verified_at` and an `expires_at`. The
fork's `multi/lib/levels.py` emits swing pivots, prior day/week highs and lows, and price-scaled
round numbers, ATR-deduped — many more levels, undifferentiated, no tier, no memory, no expiry.

**J's own market philosophy has said this the whole time:** *supply/demand zones, wait for the
return to the zone, structure shift at the zone.* If the zones are wrong, everything downstream
of them is noise — and the filter stack faithfully processed noise on 7,489 occasions.

## The part that stings, and the part that saves us

`automation/scripts/compute_levels.py` — 741 lines, the real level compiler that feeds
production — contains **zero `"SPY"` string literals.** It is *already symbol-generic*. Its
level sources are PDH/PDL/PDC from prior-session RTH-only bars, floor-trader pivots, today's RTH
high/low, premarket high/low, anchored VWAP from yesterday's session low, tier-based expiries,
and a distance-from-spot filter.

**The fork hand-rolled a worse version of a portable component that was already in this repo.**
That is the Obsidian-brain failure the rules exist to prevent: *check whether it already exists
before building it.* I did not, and it cost a six-work-package programme.

One real portability defect to fix: the distance-from-spot filter is a hardcoded **$5** — a
SPY-dollar constant that is meaningless on a $40 or $700 name. That is a parameter, not an
architecture problem, and the multi lane already solved scale-invariance with ATR-relative
bands.

## What happens next — and what does NOT

**The path to trading more tickers, end to end:**

1. **ABLATION (proves the mechanism on one variable before anything is built on it).** Re-score
   the fork's SPY signal using `compute_levels.py` levels instead of `multi/lib/levels.py`
   levels. Nothing else changes. If SPY's hit rate moves off 49.8% toward 58%, the mechanism is
   proven. If it does not, this whole thesis dies here and I report that.
2. **PORT** `compute_levels.py` into the multi lane (already symbol-generic; make the $5
   proximity band ATR-relative), replacing the homemade level generator.
3. **RE-GATE** the 9 symbols under a **fresh pre-registration**, with the headline horizon set
   from measurement (+10 min) rather than assumption, and a hit-rate channel alongside the
   mean-return channel.

**Why step 3 is not the forbidden re-slice.** The kill-list forbids threshold sweeps, "try more
names", and re-slicing the same failed data. This changes **the input the signal reads** — a
different mechanism with a stated hypothesis and its own frozen prereg. It is a new experiment,
not a re-scoring of the old one. If it also fails, the family dies for a third and final time
and I will say so.

**Still true, still binding:** nothing is armed, `Gamma_MultiCore` stays disabled until a signal
passes a gate, and live money remains J's alone.
