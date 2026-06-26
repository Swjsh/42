---
name: bull-min-triggers-floor-keep
description: Re-validated 2026-06-26 — the bull>=2-triggers block (Safe) KEEPS under the current real-fills+managed-exit engine; corrects the direction-block inventory's "structural max(2,..)" framing
metadata:
  type: project
---

Re-validated the "bull side requires >=2 filter-10 triggers" block under the CURRENT engine
(real-fills + managed exits) per J's 2026-06-26 direction-block prune directive. **Verdict: KEEP.**

**Mechanism correction (the inventory was half-wrong):** The block premise claimed it's a
structural, non-params `max(2, min_triggers)` at `orchestrator.py:767`. Reality:
- Line 767 = `bull_min_triggers = min_triggers_bull if min_triggers_bull is not None else max(2, min_triggers)`.
- Production **explicitly sets** `filter_10_min_triggers_bull` (Safe=2, Bold=1) → flows via orchestrator
  354-355/709 into `min_triggers_bull` → ternary takes LEFT branch → **the `max(2,..)` floor NEVER
  executes in production.** It's a dormant fallback for callers passing neither key.
- The real binding bull suppressor = the **params value `filter_10_min_triggers_bull=2` (Safe only)**.
  It IS a params knob, contrary to the inventory. Bold already runs bull=1 (symmetric) → this
  asymmetry is **Safe-only, not both accounts.**

**Why:** A/B on `spy_5m_2025-01-01_2026-06-18.csv`, `use_real_fills=True` + managed exits
(-0.50 caps, tp1 0.50@0.667, runner 2.5x, trail-lock 0.05/0.15), strike_offset=2:
- BLOCKED (bull=2): ALL n=128 +$3,518 sharpe 0.140 | UNBLOCKED (bull=1): n=199 -$233 sharpe -0.006.
- The 72 marginal trades unblocking adds are ALL **single-trigger level_reclaim-only bulls**:
  -$3,421 total, avg -$47.5/trade, WR 37.5%, sharpe -0.303. Textbook L102/C20 single-trigger reclaim
  with no confluence/sequence/ribbon backing. The new ITM/managed structure does NOT rescue them.
- BEARS byte-IDENTICAL between arms (+$2,217) → all J bear anchors untouched → anchor-no-regression
  trivially PASS. The floor touches only bull trades.

**RE-CONFIRMED 2026-06-26 (2nd independent run, FULL production params.json as base overrides):**
A/B 2025-01-02..2026-06-18, real fills, only `filter_10_min_triggers_bull` varied 2 vs 1:
- BLOCKED (min2): 24 bull WR 54.2% bull_total **+$14,714**; engine +$23,732.
- UNBLOCKED (min1): 70 bull WR 41.4% bull_total **-$11,857**; engine -$2,840. Delta **-$26,572**.
- The 47 single-trigger bulls the floor blocks: WR 36%, -$577/trade, **-$22,770**, neg in **5/6 quarters**
  (only 2025-Q2 +$530 n=2) → broad regime-stable loser, not a tail artifact.
- BEAR set identical both arms (+$9,017) → clean isolation, anchor bears untouched.
- ANCHOR detail: unblock ADDS the 5/01 BULLISH_RECLAIM C @ **-$2,970** on a J-WIN day (J went 721P +$470)
  → anchor edge_capture regresses (both arms negative due to large-qty ITM bear legs on anchor dates,
  a pre-existing engine trait present in BOTH arms; the unblock makes it strictly worse via the one CALL).

**How to apply:** Do NOT recommend lowering Safe `filter_10_min_triggers_bull` 2→1 — it suppresses a
homogeneous broad-based loser cohort, not winners. This is one of the FEW bull-blocks that survives
re-validation on the current engine. The dormant `max(2,..)` fallback could be normalized to
`min_triggers` for code clarity (no-op refactor, out of ratification scope). Candidate:
`strategy/candidates/2026-06-26-092656-bull-min-triggers-floor-revalidation.md`. See
[[direction-block-inventory]] (update its line-767 framing: it's a params knob + dormant fallback,
Safe-only).
