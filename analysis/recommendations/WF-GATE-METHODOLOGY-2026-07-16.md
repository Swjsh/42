# WF ratification gate — canonical redefinition (Fable, frozen 2026-07-16 ~19:45 ET)

> Pre-registered METHODOLOGY note. Freezes the walk-forward gate's computation BEFORE it
> re-adjudicates anything (Bold ATM cell, risky-3 strike table are the first consumers).
> CLAUDE.md OP-11's bar text ("WF >= 0.70") is unchanged — this note defines what WF *is*;
> doctrine already never specified the computation.

## The problem (evidence, both from 2026-07-15 runs)

- **Absolute-cell WF is structurally broken post-SS-B.** `wf = oos_mean/is_mean` is only
  defined when `is_mean > 0`; under SS-B exits + honest friction the 2025 IS half prices
  net-negative for EVERY cell INCLUDING controls — confirmed independently on both accounts
  (`bold-strike-axis-2026-07-15.json`: 6/6 cells null; `strike-ab-convention-reconciliation.json`
  job1a: 4/4 cells null). A gate no candidate or control can pass discriminates nothing.
- **Delta-form WF works.** The directional-gate battery (`directional_gate_battery.py#compute_wf`,
  same night) computed WF on the gate-ON-vs-OFF **delta**, per-trade normalized — and it
  discriminated: real, meaningfully negative WFs (−4.117 / −2.136 / −9.084), null only for
  structural reasons (n_oos=0, is_delta=0) that were themselves informative.

## Decision (Option B): A/B-delta WF, per-trade normalized

For any candidate C evaluated against control X on a shared signal cohort:

```
delta_i        = pnl_C(episode_i) − pnl_X(episode_i)     # matched episodes where both traded;
                                                          # episodes only one side trades enter
                                                          # its side at pnl, other side at 0
WF_delta       = (Σ_oos delta / n_oos) / (Σ_is delta / n_is)
GATE: is_delta_mean > 0  AND  WF_delta >= 0.70            # bar value unchanged
```

Verdict ladder (explicit, no silent nulls):
- `is_delta_mean > 0` and `WF_delta >= 0.70` → **PASS**
- `is_delta_mean > 0` and `WF_delta < 0.70` → **FAIL**
- `is_delta_mean <= 0` and `oos_delta_mean <= 0` → **FAIL** (candidate never improved anything)
- `is_delta_mean <= 0` and `oos_delta_mean > 0` → **INSUFFICIENT_REGIME_SHIFT** — park, never
  auto-ratify; re-test when the OOS window has grown by >= 50% or n_oos >= 30. (A candidate
  that helps only in the newest regime may be real, but it cannot clear an anti-overfit gate
  on the very data that suggested it.)

## Why B over A (rolling-origin 2026-only WF)

1. **It answers the actual ratification question.** Every OP-11 decision is "is this CHANGE
   better than the status quo, stably across time" — a paired question. Absolute WF conflated
   the knob's effect with the era's profitability; the 2025-negative base is a property of the
   ERA under SS-B pricing, not of any candidate.
2. **Keeps both years.** Option A discards 2025 entirely; B keeps it as paired-difference
   evidence, where regime drift largely differences out (paired design, lower variance).
3. **Already validated in production use.** The gate battery ran exactly this form the same
   night and produced discriminating verdicts; choosing B standardizes existing practice
   rather than inventing a third form.
4. **A's folds are too thin.** 2026 YTD gives ~6.5 months; K-fold rolling origin on cells with
   n_oos ≈ 50-90 yields folds of n≈10-20 — variance swamps signal at our n.

## Mandatory disclosures (every scorecard using this gate)

- State the WF form used (`wf_form: "ab_delta_per_trade_v2026_07_16"`).
- Compute the same WF for a null/control sanity cell; if the gate is undefined or unreachable
  for the sanity cell too, flag `wf_not_discriminating: true` and rest the verdict on the
  remaining gates with the anomaly disclosed (the 2026-07-15 discipline, now standing rule).
- Absolute-cell WF may still be REPORTED as a descriptive statistic; it no longer gates.

## Retro-application queue (first consumers)

1. **Bold ATM cell** (`bold-strike-axis-2026-07-15.json` near-miss, 4/5 gates): re-adjudicate
   vs OTM-3 control under delta-WF on the shared episode set. NOTE: a PASS here changes the
   cell's evidence status only — the live tier flip REMAINS parked for J's explicit words
   (standing commitment, three independent holds; gate outcomes do not override it).
2. **risky-3 nearer strike table** (same study family).
3. Prospectively: all future strike/exit/gate A/Bs.

Frozen. Any change to this computation requires a successor note superseding this one by name.


---

## AMENDMENT 1 (Fable, 2026-07-16 ~20:40 ET — same night, found by first application)

The INSUFFICIENT_REGIME_SHIFT re-test trigger as originally frozen ("OOS window grown >= 50%
or n_oos >= 30") is defective: n_oos >= 30 can already be satisfied by the data present AT
adjudication (Bold ATM adjudicated with n_oos=86), making the trigger vacuous. CORRECTED
trigger, superseding the original sentence: re-test when EITHER (a) the OOS window has grown
>= 50% in calendar length SINCE the adjudication date, OR (b) >= 30 NEW episodes (post-
adjudication) have accrued in the cohort. All quantities relative to the adjudication
snapshot recorded in the scorecard. First consumer: bold-strike-axis-deltawf-readjudication-
2026-07-16 (adjudicated 07-16; re-test earliest ~30 new cohort episodes or ~mid-October 2026
window growth, whichever first).

Nothing else in this note changes. The verdict ladder, pairing rule, disclosures, and the
0.70 bar are untouched.
