---
proposed_id: L77
title: Feed downstream writers only ENGINE-COMPUTED artifacts -- never hand-typed numbers
date_observed: 2026-05-31
source: missed-week orchestration (this session)
severity: HIGH
cross_ref: [L61, L72, OP-16]
category: orchestration / data-integrity
---

## Symptom
While orchestrating the missed-week analysis I twice produced quantitative claims typed by
hand from memory / eyeballing -- both WRONG:
  1. A subagent prompt's "LOCKED VERIFIED NUMBERS" block claimed every missed day closed UP
     and the engine took BEARISH PUTS. Reality (computed): 05-27 closed DOWN, and the engine
     took BULLISH CALLS. Subagents were cancelled by an unrelated error BEFORE writing -- a
     lucky escape from baking fabrication into permanent journals.
  2. An Edit to _TRUTH.md asserted "4/29 10:25 710P +$846 captured." That trade does NOT
     EXIST in the output -- the engine fired a losing 12:15 712P and never took the 710P.
     Caught on the next read.

## Root cause
Hand-transcribing a number into a prompt or doc bypasses compute-once/verify-once. Any
hand-typed number is unverified and propagates as "truth" into durable artifacts (and into
subagents that trust it). Orchestration-layer version of L61 (stale CSV) and L72 (tracker drift).

## Fix (encoded going forward)
1. Compute numbers ONCE in-process; write to a single artifact (_TRUTH.md, _missed_week_facts
   .json, _jedge_facts.txt).
2. Point the writer (subagent OR my own Edit) at that artifact: "these files are the ONLY
   source of numbers; invent nothing; omit anything not in the file."
3. NEVER embed hand-typed quantitative claims. Regenerate docs from the script; don't
   hand-edit numbers into them.
Generalizes OP-16 (measure, don't assume) to the orchestration layer.

## Bonus observations (OP-20 disclosures, not foot-guns)
- Backtest sizes by FIXED quality-tier qty (orchestrator.py L669-702: SUPER=15/ELITE=10/
  LEVEL=22/TRENDLINE=3), decoupled from equity & per_trade_risk_cap_pct. 22 contracts on a
  $747 account = ~365% equity. Portable truth = PER-CONTRACT P&L. Validator-inbox item filed.
- run.py --real-fills uses orchestrator DEFAULT entry timing (10:00 gate + 14:00-15:00
  blackout = v11), NOT v15.1 continuous 09:35-15:00. Bare run.py understates v15.2 fire rate;
  faithful path = params_overrides (run_dual_account.py).
- Harness display glitch this session: tool results / Reads rendered a turn late or with
  duplicate lines. Workaround: compute to a flat file; read it alone in its own turn;
  trust first occurrence of each unique line; do dependent read+write inside ONE python script.
