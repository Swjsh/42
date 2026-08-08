# EOD-flatten's -MaxBudgetUsd 1 was chronically too tight for its tool-call-heavy retry loop (3rd recurrence of the "budget mis-sized at birth" class)

**Filed:** 2026-08-08 (conductor WEEKEND fire, EOD-FLATTEN-LLM-PROMPT-EXIT1, itself filed
2026-08-06 by VBS-WRAPPER-EXIT-CODE-BLIND-SPOT's masked-exit finding)

## What happened

`setup/scripts/run-eod-flatten.ps1` / `run-eod-flatten-aggressive.ps1` invoke the LLM-prompt
EOD-flatten path (`automation/prompts/eod-flatten.md` / `aggressive/eod-flatten.md`) with
`-MaxBudgetUsd 1`, unchanged since creation (2026-06-21). Live logs
(`automation/state/logs/eod-flatten{,-aggressive}-<date>.log`) show `Error: Exceeded USD
budget (1)` -> exit=1 on a recurring basis:

- `eod-flatten-aggressive`: exit=1 on 08-03, 08-04, 08-05, 08-06, 08-07 (5/5 dates checked)
- `eod-flatten` (safe): exit=1 on 08-05, 08-06, 08-07; exit=0 on 08-03, 08-04

Not a realized safety incident -- the deterministic `Gamma_EodFlattenCore` backstops both
accounts and fires ~3 min earlier, confirmed flat both accounts every date checked via
`engine-health.json`. But the documented LLM path (which ALSO does fill-reconciliation
against `journal/trades.csv` and a dashboard-dialogue update the deterministic core does not)
was silently degraded to backup-only on a majority of days.

## Root cause (one sentence)

`eod-flatten.md`'s retry-until-zero close loop (up to 3 attempts x ~4 MCP calls each) plus a
fill-reconciliation pass is tool-call-heavy enough that `-MaxBudgetUsd 1` was never realistic
headroom -- it was mis-sized at birth, not a regression.

## Why this is a re-violation, not a new class

This is the **3rd time** this exact shape has been found in ~1 week:
- 2026-08-06: `run-scout-premarket.ps1` `-MaxBudgetUsd 0.50` -> daily exit=1 for ~7-8 weeks
  (`test_scout_premarket_budget.py`).
- 2026-08-06 (same STATUS.md batch): `queue.md` filed `BUDGET-ROSTER-AUDIT-MAXBUDGETUSD`
  (MED) as the explicit follow-up -- "audit all `-MaxBudgetUsd` values roster-wide for the
  same class of outlier" -- **still `status:pending`, never executed.**
- 2026-08-08 (this fire): `run-eod-flatten{,-aggressive}.ps1` `-MaxBudgetUsd 1` -> the exact
  same failure signature, on the EOD-safety-net class of task this time.

Per OP-25, a lesson that re-violates in the wild MUST graduate to a code assertion, not stay
prose. Fixed THIS instance with `backtest/tests/test_eod_flatten_budget.py` (mirrors
`test_scout_premarket_budget.py`'s pattern exactly: pins the known-broken value + a floor).
But per-script guards only catch scripts someone already investigated -- they do not prevent
a 4th recurrence on an untouched script.

## Suggested graduation (bounded, for a future fire -- not attempted this fire, single-item scope)

`BUDGET-ROSTER-AUDIT-MAXBUDGETUSD` (already queued MED) should not just be a one-time audit --
it should ship a STANDING guard: a single parametrized test
(`test_budget_roster_no_known_broken_outliers.py` or similar) that walks every
`run-*.ps1` invoking `Invoke-Claude`/`Invoke-ClaudeWithRetry`, classifies task "weight" by
prompt file size + MCP-tool-call density (heartbeat-tier / premarket-tier / EOD-tier), and
asserts each `-MaxBudgetUsd` clears a tier-appropriate floor -- so the NEXT under-budgeted
script is caught by CI/the curated safety gate instead of by a 4th live-log archaeology fire.
