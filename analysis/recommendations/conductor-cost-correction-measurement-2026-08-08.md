# CONDUCTOR-BUDGET-ARITHMETIC -- independent re-measurement (2026-08-08)

**Verdict: the arithmetic-artifact hypothesis is FALSIFIED.** `SELF_REPORT_CORRECTION` was
re-measured (2.20 -> 2.16) off real transcript data and the change is defensible, but a full
32-day replay proves it changes **zero** historical fire-slot outcomes. The week's 20-of-45
slot starvation is not explained by the correction factor being wrong. Full machine-readable
data: [`conductor-cost-correction-measurement-2026-08-08.json`](conductor-cost-correction-measurement-2026-08-08.json).

## 1. Provenance of the original 2.2

Traced to `setup/scripts/conductor_budget.py`'s own module docstring + commit `c96bdaf0`
(2026-07-25): *"conductor reports $3.44/fire vs $7.69 real."*

**No standalone census script or intermediate data artifact survives anywhere in the repo.**
Searched: every doc/markdown/analysis file mentioning "2.2", `git log -S` on
`conductor_budget.py` for the constant's introduction, and the one same-dated spend snapshot
that exists (`automation/state/spend-2026-07-25.json`). That snapshot is an **all-Claude-
sessions-that-day** aggregate ($423.39 across sonnet/opus/haiku, 12 sessions) -- not
conductor-specific, and it reproduces neither $3.44 nor $7.69 in any field. The module's own
OP-33 comment already flagged this: *"no re-measurement... has been done since that single
2026-07-25 census."* Sample size of the original census is likewise never stated.

**Finding: the $3.44/$7.69 figures exist only as prose.** The original derivation is not
reproducible from anything in the repository.

## 2. Independent measurement

Built [`backtest/tools/measure_conductor_cost.py`](../../backtest/tools/measure_conductor_cost.py):
for each `conductor-outcomes.jsonl` row, finds the matching Claude Code session transcript
(`~/.claude/projects/C--Users-jackw-Desktop-42/*.jsonl`) by (a) a literal marker string unique
to `conductor.md`'s STAGE-0 text (`"rail-0 budget gate"`) and (b) nearest-timestamp matching
(session's last activity within 15 min of the outcome row's `fired_at`, greedy one-to-one).
Real cost = every assistant-turn's actual token usage x Anthropic's published per-token
pricing -- same methodology `setup/scripts/spend_summary.py` / `setup/scripts/token_forensics.py`
already use for day-level reporting, applied here per-fire.

Session transcripts only survive from 2026-07-09 onward (older ones are gone), so only fires
from that date forward are matchable. Of 280 outcome rows, 70 matched a transcript.

### Two populations, two different stories

**Real-work fires** (self-report >= $0.25, n=16, spanning 2026-07-26..2026-08-08):

| Stat | Value |
|---|---|
| n | 16 |
| median ratio (real/self) | 1.81x |
| mean ratio | 4.35x (right-skewed) |
| range | 1.41x -- 14.18x |
| **dollar-weighted aggregate** (sum(real)/sum(self)) | **2.155x** |

All 16 individual ratios are `> 1.0` -- self-report under-counts in every single matched fire,
100% directional consistency. The dollar-weighted aggregate (2.155, rounds to 2.16) is the
statistic used to update the constant, because that is how the constant is actually applied:
multiplied into a **sum** of a day's self-reports, not averaged per-fire ratios.

The spread (1.4x for "shippy" fires up to 14.2x for investigation-heavy audits) means a single
flat multiplier is a crude, average-case model no matter what value it holds -- it will always
over-correct some fires and under-correct others.

**Near-zero-self-report fires** (self-report < $0.25, n=54 -- the STAGE-0 budget-gate-exit
no-ops that now fire repeatedly per day): self-report sums to **$0.45 total**; real cost sums
to **$67.38 total** -- an average of ~$1.25 real dollars per fire that self-reports essentially
$0.00. This is a **separate, structural** failure mode: reading `CLAUDE.md` + `conductor.md` +
the full MCP tool-schema surface + the state digest is a large fixed token cost paid on every
fire regardless of how little work follows, and **no multiplicative constant can fix it**
(`0 x anything == 0`). Every repeated EXHAUSTED re-check (7+ observed in a single day, e.g.
2026-08-08) burns real notional spend invisible to the $30 cap, in either direction, regardless
of `SELF_REPORT_CORRECTION`'s value. Flagged as a follow-up -- fixing it would mean editing
`conductor.md` / `run-conductor.ps1`, both outside this task's authorized file surface.

Caveat: 0 `isSidechain:true` events were found anywhere in the 605-file transcript corpus
scanned, so there is no positive evidence either way on whether `Agent()`-tool sub-agent
fan-out inside a conductor fire gets recorded in the parent transcript. If it is NOT recorded,
every "real cost" figure above is a **lower bound**, and the true under-report is larger still
-- never smaller.

## 3. The subscription question

**Verdict: (c) a quota / rate-limit-pool consumption proxy -- not real incremental money, and
not billed per API call either.**

Evidence:
- `run-conductor.ps1` -> `_shared.ps1`'s `Invoke-Claude` launches the local npm `claude.exe`
  with `--print --max-budget-usd ... --model ... --effort ...`. No `--api-key` flag and no
  `ANTHROPIC_API_KEY` assignment anywhere in `_shared.ps1` (grepped, zero matches) -- auth is
  the same OAuth/subscription session as J's interactive CLI login.
- CLAUDE.md OP-3: *"$200/mo Max 20x plan budget"* -- a flat monthly subscription, not metered
  per-token billing.
- `spend_summary.py`'s own docstring states this outright: *"The Max plan covers spend up to
  the rate-limit budget; this report is the METER that tells us how close we are. A high
  $-day doesn't cost J extra (Max is flat $100/mo), but it predicts the next rate-limit hit."*
- Every dollar figure anywhere in this system -- the self-report, `conductor_budget.py`'s
  `corrected_usd`, `spend_summary.py`, `token_forensics.py`, and this measurement's
  `real_cost_usd` -- is the **same notional computation**: tokens x Anthropic's published
  per-token API price. None of it is an actual invoice line.

**Implication:** the $30/day cap is a proxy for how much of the shared Max rate-limit pool got
consumed, not a dollar budget. Re-deriving the correction factor keeps the measurement pointed
in the right *relative* direction (bigger notional $ ~ more real resource burned), but USD is
arguably the wrong *unit* to reason about precision in -- tokens or wall-clock would track the
actual binding constraint (rate-limit walls) more directly. This is flagged, per the task
brief, as a bigger finding than the exact factor value -- **not implemented here**, since no
file in this task's authorized surface redesigns the budget's unit.

## 4. Decision: constant updated, 2.20 -> 2.16

`n=16` clears the `n>=5` bar with unambiguous direction (100% of ratios > 1.0) and a stable,
reproducible aggregate point estimate (2.155). `SELF_REPORT_CORRECTION` in
[`setup/scripts/conductor_budget.py`](../../setup/scripts/conductor_budget.py) was updated to
`2.16`, cited to this measurement file, with a new guard test
(`test_self_report_correction_matches_2026_08_08_remeasurement` in
`backtest/tests/test_conductor_budget.py`) pinning it. The full test file (44 tests, including
2 pre-existing tests whose hardcoded dollar literals were arithmetic-only updates to track the
new constant) is green.

**This is an accuracy correction, not a starvation fix** -- see the replay below.

## 5. Slot-per-day replay: current (2.20) vs measured (2.16)

Chronological per-ET-day admission replay of every row in `conductor-outcomes.jsonl` (32 real
ET-days, 280 rows) under `conductor_budget.py`'s actual shipped defaults (`daily_cap_usd=30`,
`max_fires=4`, pacing disabled per the 2026-08-08 revert), varying only
`SELF_REPORT_CORRECTION`. A fire is "admitted" iff `prior-cumulative-raw x factor < $30 AND
fires-so-far < 4`; a blocked fire never runs, so it never adds to the cumulative.

| | current (2.20) | measured (2.16) |
|---|---:|---:|
| Total slots used, 32 days | 112 | 112 |
| Avg slots/day | 3.50 | 3.50 |
| Days hitting the `max_fires=4` hard ceiling | 23 | 23 |
| **Days where the two constants disagree** | **0 of 32** | |

**2.20 -> 2.16 changes admission on zero of 32 real historical days.** For reference, a
sensitivity sweep shows the factor has to move much further before slot counts shift at all
(114 slots at factor=1.0, 112 at 2.16-2.20, 102 at 3.09 [the all-population aggregate including
near-zero fires], 65 at 7.69). 23 of 32 days (72%) are bound by the `max_fires=4` hard ceiling
regardless of dollar arithmetic; on the remaining cap-bound days, real self-reported dollar
amounts from a handful of $3-9 real-work fires are large enough that a 2% change in multiplier
never flips a single admission decision.

**Conclusion for the operator:** the correction constant was not, and never was, the reason
slots went unused this week. If slot starvation itself needs fixing without raising the $30
cap (OP-3 forbids that), the two candidate levers are structural, not arithmetic:
1. Stop counting a budget-exhausted early-exit re-check against `max_fires` (it does zero
   incremental work but still consumes a "fire" slot under the current count).
2. Reduce real per-fire spend directly (smaller `--max-budget-usd`, lower effort tier for
   fires that historically don't ship).

Both require editing `conductor.md` / `run-conductor.ps1`, outside this task's authorized file
surface -- reported here as the next queue item, not implemented.

## Known stale prose (not fixed here -- outside authorized file surface)

- `automation/prompts/conductor.md` STAGE-0 text still says *"corrects your self-report x2.2"*
  (now 2.16).
- `setup/scripts/autonomy_report.py`'s module docstring still cites *"a 2.2x self-report
  correction."*

Both are cosmetic (the actual gate logic reads the live constant dynamically) but should be
updated for consistency next time either file is touched for an authorized reason.

## Files

- Measurement tool: `backtest/tools/measure_conductor_cost.py`
- Guard tests: `backtest/tests/test_measure_conductor_cost.py` (15 tests, all green)
- Updated: `setup/scripts/conductor_budget.py` (`SELF_REPORT_CORRECTION = 2.16`, cited)
- Updated: `backtest/tests/test_conductor_budget.py` (+1 pinning test, 2 pre-existing tests'
  hardcoded literals corrected for the new constant, docstring note added)
- Raw data: `analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.json`
