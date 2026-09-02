# PDT-BLOCKED-COUNTERFACTUAL-2026-08-11 -- runner result (pdt-blocked-counterfactual-2026-09-02.json)

**Verdict: FAIL_PDT_STAYS_AS_IS**

## Naive-counterfactual limitation (restated prominently, per the frozen prereg)

> Taking a blocked trade would have shifted the rolling PDT window and could have blocked a DIFFERENT later trade. This measures the marginal value of the blocked intents in ISOLATION, not a full sequential re-simulation. **A positive result licenses a forward trial, never a direct ship.** n=18 is below the advisory n>=20 bar -- a pass is SUGGESTIVE, not sufficient on its own. PDT stays exactly as-is for live accounts under $25k regardless of this result -- that is a real regulatory rule and is NOT being questioned here.

## Population (re-derived from core-decisions.jsonl, not copied from the prereg)

- RISK_DENY_PDT attempts: **68**
- unique (account,symbol,date) intents: **18**
- date range: ['2026-07-08', '2026-08-07'], 9 days

## Harness validation (validate the validator)

- n = 43 anchor positions (safe-2/bold-2, engine-attributed, 2026-07-08..2026-08-07)
- **sign agreement: 95.3%** (bar: 85%) -> RELIABLE
- actual total $-538 vs replay total $-2,202, median abs error $32

## Gates

| Gate | Pass | Detail |
|---|---|---|
| G1 net_positive | False | net_total = $-11.20 |
| G2 day_balance | False | 2 profitable vs 7 losing days |
| G3 drop_best | False | net - best_day = $-1,390.50 (best day 2026-08-04: $+1,379.30) |
| G4 not_concentrated | False | best day = None of net |
| **ALL PASS** | **False** | |

Days priced: 9

## Deviations from the frozen design

- SPY260713P00750000 (2026-07-13, safe): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).
- SPY260714P00752000 (2026-07-14, safe): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).
- SPY260730P00735000 (2026-07-30, bold): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).
- SPY260805P00771000 (2026-08-05, bold): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).
- SPY260805P00772000 (2026-08-05, bold): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).
- SPY260806P00770000 (2026-08-06, bold): post-STOP-B date but the ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a genuine data gap (schema/telemetry miss), not a policy choice. Priced anyway (disclosed here, not hidden).

## Capital-non-binding assumption violated for:

- safe SPY260708P00744000 2026-07-08: notional $543 > 30% risk cap $454 at equity $1,513
- bold SPY260730P00735000 2026-07-30: notional $1,060 > 50% risk cap $599 at equity $1,198

## Per-intent detail

| Date | Account | Symbol | Qty | Entry | PnL | Legs |
|---|---|---|---|---|---|---|
| 2026-07-08 | bold | SPY260708C00749000 | 5 | $0.17 | $-22.00 | 1 |
| 2026-07-08 | bold | SPY260708P00741000 | 5 | $0.26 | $-31.00 | 1 |
| 2026-07-08 | safe | SPY260708C00746000 | 3 | $1.06 | $-66.60 | 1 |
| 2026-07-08 | safe | SPY260708P00744000 | 3 | $1.81 | $+540.00 | 2 |
| 2026-07-13 | safe | SPY260713P00750000 | 3 | $1.10 | $-69.00 | 1 |
| 2026-07-14 | safe | SPY260714C00752000 | 3 | $1.19 | $-181.50 | 1 |
| 2026-07-14 | safe | SPY260714P00752000 | 3 | $0.74 | $-47.40 | 1 |
| 2026-07-28 | bold | SPY260728C00741000 | 5 | $0.88 | $-225.00 | 1 |
| 2026-07-30 | bold | SPY260730P00735000 | 5 | $2.12 | $-217.00 | 1 |
| 2026-08-04 | bold | SPY260804C00769000 | 5 | $1.27 | $+638.80 | 2 |
| 2026-08-04 | bold | SPY260804C00770000 | 5 | $0.96 | $+482.00 | 2 |
| 2026-08-04 | bold | SPY260804C00771000 | 5 | $1.14 | $+551.00 | 2 |
| 2026-08-04 | bold | SPY260804C00772000 | 5 | $1.15 | $-292.50 | 1 |
| 2026-08-05 | bold | SPY260805P00771000 | 5 | $1.42 | $-147.00 | 1 |
| 2026-08-05 | bold | SPY260805P00772000 | 5 | $1.85 | $-190.00 | 1 |
| 2026-08-06 | bold | SPY260806P00770000 | 5 | $1.19 | $-124.00 | 1 |
| 2026-08-07 | bold | SPY260807C00772000 | 5 | $1.25 | $-317.50 | 1 |
| 2026-08-07 | bold | SPY260807C00773000 | 5 | $1.15 | $-292.50 | 1 |
