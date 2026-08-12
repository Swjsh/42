---
filed: 2026-08-11
filed_by: goal fire (unlock-more-trades, ~21:00-01:30 ET)
kind: lesson
status: pending
---

# A qty counterfactual computed as `pnl_per_contract x wanted_qty` returned the WRONG SIGN — and a `(arm, symbol, date)` join key silently double-counted split fills

Two independent analysis defects in ONE study, each of which alone would have shipped a
false verdict. Both were caught by process, not luck. The study: does the recency qty-clamp
(`fleet_executor._apply_recency_min_sizing`) cost or save money?

## Symptom

Three different answers to the same question, in sequence:

| pass | method | answer |
|---|---|---|
| 1 | linear: `pnl/qty * wanted_qty` | unclamping **EARNS +$1,254** |
| 2 | real replay, `(arm,symbol,date)` join | unclamping **LOSES −$2,135** |
| 3 | real replay, per-fill timestamp join | unclamping **LOSES −$876** ← correct |

Pass 1 and pass 2 disagree on **sign**. Pass 2 and pass 3 disagree by **2.4x**.

## Root cause

**Defect A (wrong sign).** The linear estimate assumed P&L scales linearly with qty. It does
not in general: `exit_manager`'s `tp1_qty_fraction` partial scale-out rounds differently at
different qty, changing the runner-leg fraction (at qty 3 the runner is 1/3; at qty 8 it is
3/8). A counterfactual that changes qty MUST re-walk the exit machine, never rescale a scalar.

**Defect B (double-count).** The wanted-qty lookup was keyed `(arm, symbol, date)`. That key
is **not unique per fill** — safe-3 split 2+1 lots on the same contract at 11:52 on 08-04, and
several arms re-entered the same strike the same day. Every fill sharing a key received the
FULL wanted qty, so a 2+1 split became 8+8=16 contracts instead of 8.

## How each was caught (the reusable part)

- **Defect A** was caught by the **prereg**, which had flagged linear scaling as an untrusted
  assumption BEFORE the runner and mandated a non-linear replay as the method. The prereg was
  written while the linear number was the only number in hand.
- **Defect B** was caught by **refusing to report an unexplained sign flip**. Rather than
  publishing "the replay disagrees with the estimate," the mechanism was traced on ONE
  position at both qtys: per-contract P&L came back *identical* (+$81.8), proving the walker
  DOES scale linearly for a single fill — which contradicted the aggregate and localised the
  bug to the join, not the model.

## Fix

Per-fill join: decision rows matched to fills by nearest timestamp within 300 s, each decision
row consumed at most once (`used` flag).

## Rule to carry forward

1. **Any counterfactual that changes qty, size, or leg count must re-run the exit machine.**
   Rescaling a P&L scalar is only valid if you have PROVEN linearity for that transform.
2. **A join key over a trade population must be unique per FILL.** `(arm, symbol, date)` is
   not — same-day re-entries and split fills are normal in this book. Assert
   `len(keys) == len(rows)` or join on timestamp.
3. **Never report a sign flip you cannot explain mechanically.** An unexplained reversal
   between two methods means at least one is broken; find which before publishing either.

Sibling of C14 (dead/mistranslated knobs) and C7 (silent success). Closest existing kin:
L251 (two replay engines silently disagreed — diff PER-TRADE by terminal stage, not aggregate).
