# TRANSPLANT VERDICT: levels are NOT the missing input — and I said otherwise too early (2026-08-21)

> Run as frozen in `analysis/recommendations/prereg-multi-levels-transplant-2026-08-20.json`.
> Harnesses: `backtest/tools/multi_levels_transplant.py` (9 symbols, paired),
> `backtest/tools/spy_full_levels_control.py` (SPY, 3 arms). Raw:
> `analysis/multi-lane/levels-transplant.json`, `analysis/multi-lane/spy-full-levels-control.json`.

---

## CORRECTION FIRST

Earlier in this session I told J: **"the levels ARE the edge."** That was a hypothesis reported
as a finding, and it is now falsified. The correction matters because it changes what to build:
if levels were the gap, the fix was a port; they are not, so the fix is elsewhere.

What I actually had at the time was one true observation — the production trigger and the forked
trigger score very differently — and one *guess* about why. I should have said "the most likely
cause is the levels, and here is the test." I said the conclusion instead.

## THE RESULT

**SPY control, three arms, identical bars and identical filter stack, zero errors:**

| arm | level source | avg levels | hit @ +10min | sigma |
|---|---|---|---|---|
| fork | `multi/lib/levels.py` (home-made) | 33.2 | 51.08% | +0.53 |
| prod_base | `reconstruct_levels` (1 of 4 families) | 9.8 | 48.90% | −0.53 |
| **prod_full** | **`level_records_asof` (all 4 families)** | 10.0 | **48.97%** | **−0.52** |

**All nine symbols, paired, both arms:**

| | SPY | QQQ | IWM | NVDA | AAPL | TSLA | MSFT | AMD | GLD |
|---|---|---|---|---|---|---|---|---|---|
| fork hit | 51.08 | 47.98 | 51.85 | 48.95 | 48.71 | 47.96 | 47.54 | 46.65 | 49.31 |
| prod hit | 48.90 | 49.05 | 49.79 | 50.08 | 51.27 | 49.92 | 46.76 | 47.46 | 45.70 |
| delta | −2.18 | +1.07 | −2.06 | +1.13 | +2.56 | +1.96 | −0.78 | +0.81 | −3.61 |
| sigma | −0.53 | −0.46 | −0.09 | +0.04 | +0.55 | −0.04 | −1.46 | −1.10 | −1.50 |

**Every symbol, every arm, fails its null.** The largest sigma anywhere is +0.55. The deltas from
swapping the level source run −3.61 to +2.56 with no consistent sign — noise, not signal.

Per the frozen rule this is **FAIL**: the control did not recover, and giving the trigger
production-grade levels changed nothing.

## What this does and does not establish

**Established, and unchanged:** the production trigger has real directional information —
58.23% at +10min on n=881, **+4.89 sigma**. The forked trigger does not — ~49% on 7,489 signals,
and now ~49% again on 5,300 more across three level sources.

**Newly established:** the gap between them is **not** the levels. Four families of
production-grade levels, correctly composed, admitted by production's own expiry and
proximity rules, moved the forked trigger by nothing.

**Therefore, by elimination:** the difference lives in the **filter stack itself**.
`multi/lib/filters.py` (1,211 lines) is a *re-implementation* of production's scoring, not the
same code. A re-implementation that scores 49% where the original scores 58% is not a port; it
is a different strategy wearing the same filter names.

## Two process failures worth keeping

1. **A broken arm reported a plausible number.** The first `prod_full` run raised on 89 of 477
   level refreshes — an input-contract mismatch (`prior_day_levels` indexes a `date` column I
   never supplied). The errors were *counted* but not *printed*, so the arm returned a
   perfectly reasonable-looking 47.10% that meant nothing. Counting an error and not surfacing
   it is the same as swallowing it. The harness now prints the error rate and flags any arm
   above 1% as `*** ARM UNTRUSTWORTHY ***`.
2. **My "curated levels loaded" detector was wrong**, so I briefly believed the curated family
   was absent when the snapshot archive covers 20 days of the window. Measuring whether an
   input arrived is itself an instrument, and it needs the same scepticism as the result.

Both are instances of the rule this shop keeps re-learning: **the instrument is part of the
experiment.** Tonight's whole thread started because the harness disagreed with a
known-profitable engine, and it has now caught two of its own defects.

## What ships for Friday, and what does not

**SHIPS — the per-ticker evaluation system** (`multi/evaluate.py`, `Gamma_MultiEvaluate`,
09:00 ET premarket then every 30 min). For every name: the tiered zone map with supply/demand
shelves and distances in percent *and* ATR, market structure (HH/HL/BOS/CHoCH), relative volume,
VIX regime, per-side scores with **named** triggers and **named** blocking filters, and for the
top names the concrete prospective trade — contract, strike, expiry, premium, spread, size,
dollar risk, catastrophe cap. Every field is a real measurement or an explicit `UNAVAILABLE`
with a reason.

**DOES NOT SHIP — entries on non-SPY names.** There is no validated signal for them. Tonight
did not weaken that position; it strengthened it, by ruling out the most plausible fix. Arming
would break Rule 1 (no setup, no trade) and Rule 10. The lane stays STOPPED and
`Gamma_MultiCore` stays disabled.

## The honest next step

Stop patching the fork. The production signal path — `build_shared_signal.py`, 1,288 lines,
**zero SPY string literals** — is the thing with a measured 58.23% / +4.89σ edge. The open
question is what it would take to run *that* on other symbols: its code carries no hardcoded
ticker, but its `build()` entry point reads SPY-specific state files rather than taking a symbol
argument, so this is real work, not a parameter flip. I am explicitly **not** claiming it will
transfer — that is exactly the mistake this document opens by correcting. It is the next
hypothesis, and it gets its own pre-registration and its own null gate before anything is built
on top of it.
