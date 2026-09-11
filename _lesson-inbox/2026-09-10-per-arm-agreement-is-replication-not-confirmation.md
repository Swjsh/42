---
kind: lesson
date: 2026-09-10
source: GOAL-WHY-THIS-WEEK-2026-09-10 W12
---

# Per-arm agreement is REPLICATION, not independent confirmation

**Symptom.** The engine's single best day (2026-08-04, +$3,624 — more than the entire engine
era's net P&L) reads like a broad, robust win: six arms profitable, five different account
ledgers all green. Decomposed by wave it is **two market events**:

- 09:50 → `SPY260804C00763000`, taken by bold-2, risky-1, risky-3 (x3), safe-2, safe-3 = +$2,350
- 12:20 → `SPY260804C00769000`, taken by risky-1, risky-3, safe-2, safe-3 = +$2,192
- the day's other six waves were net negative

**Root cause.** Arms are **risk profiles on one shared signal**, not independent strategies —
this is settled doctrine (`feedback_arms_are_risk_profiles_not_strategies`). They differ only
by sizing/gates/stop. When N arms take the same signal, that is ONE draw from the edge
distribution recorded N times. Summing per-arm P&L and reading the agreement as corroboration
inflates the apparent evidence count by the arm multiplier — here, up to **7x**.

**Fix / how to avoid.**
- **Wave-dedupe before ANY evidence claim.** One ~10-minute bucket on one contract = one
  market event, regardless of how many arms or qty-split CSV rows it produced.
- Per-arm totals are fine for *attribution* ("which risk profile monetised the signal best")
  and are the wrong unit for *evidence* ("how many times has this edge fired").
- The same error in the other direction: this week's "0 for 7 trades" was really **0 for 4
  waves** — three arms on one 12:1x signal. Naive counting made a 19%-likely week look 5.6%-likely.
- Applies to n-counting everywhere: bootstrap samples, FDR corrections, tail-day frequency,
  and any "n independent confirmations" claim.

**Second-order.** Concentration analysis must run on deduped waves too. "Top 1 day = 1038% of
total net" understates the problem once you see that day is really two events.
