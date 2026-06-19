# Auto-Decision-Trace on Near-Misses (D3)

**Status:** DRAFT — proposal only. Do NOT modify heartbeat.md without J ratification.
**Date:** 2026-06-15
**Phase:** 4 — Live-path robustness
**Task:** AC-4.2
**Type:** Infrastructure / observability

---

## Problem

Near-miss ticks (bear>=8 or bull>=9 with no ENTER action) are already logged in
`decisions.jsonl` with a free-text `reason` field. The root blocker is buried in prose:

```
"reason": "5m ribbon BULL-stacked, spread 14c blocks filter_6; developing 9/11..."
```

Machine-readable analysis (L80 shadow grading, weekly review clustering, Kitchen
cook tasks) can't reliably extract the primary blocker from free text. Result:
near-misses accumulate but never get systematically reviewed.

---

## Proposal: `near_miss_trace` structured field

When a heartbeat tick qualifies as a near-miss (bear>=8 OR bull>=9 AND action != ENTER),
the heartbeat appends a `near_miss_trace` object to that tick's decisions.jsonl row.

### Field spec

```json
"near_miss_trace": {
  "side": "bull",                       // "bull" | "bear"
  "score": 9,                           // N passes of 11 total
  "max_score": 11,
  "primary_blocker": 6,                 // filter number (int) — the ONE filter that alone
                                        // would allow entry if fixed. If multiple, pick
                                        // the one with highest historical flip-to-entry rate.
  "secondary_blockers": [8, 10],        // other still-failing filters
  "setup_name": "BEARISH_REJECTION",    // matched playbook pattern or null
  "is_first_near_miss_today": true,     // first near-miss of same side today
  "same_setup_stopped_out_today": false,// this setup already had a stop-loss today (Rule 4)
  "trigger_fired": true,                // did a named trigger fire this tick?
  "trigger_name": "level_reclaim",      // normalized trigger name (L79: no price suffix)
  "confidence_tier": "NEAR_MISS_HIGH",  // NEAR_MISS_HIGH (score>=10) / NEAR_MISS_MED (8-9)
  "manual_review_flag": false           // set true by J or dashboard override
}
```

### Primary blocker assignment rule

```
primary_blocker = argmin(filters_blocked, key=lambda f: historical_flip_rate[f])
```

**Actual live data (2026-06-16 near_miss_audit.py — safe account, N=25 near-misses with filter_state in 14/25 rows):**
- Filter 11 (second trigger confirmation) blocks 28% → **most common blocker**
- Filter 6 (ribbon spread < 30c) blocks 16%
- Filter 10 (HTF veto) blocks 16%
- Filter 5 (ribbon direction mismatch) blocks 8%
- Note: 44% of near-miss rows lack filter_state (early-era rows, pre-dates structured logging)
- Note: 24/25 safe near-misses are BULL-side (engine is BEARISH_REVERSAL only → all BULL=near-miss)
- Aggressive: 90/91 near-miss rows have no filter_state (pre-structured-logging era)
- Baseline claim of "filter_6=68%" was wrong — filter_11 is dominant. After ENTER_DECISION_LOGGING_GAP_FIX ships, re-run for complete picture.
- Script: `backtest/tools/near_miss_audit.py`, output: `analysis/recommendations/near-miss-audit.json`

If no single filter can be identified as primary (all pass after one flip = impossible),
emit `primary_blocker: null` and list all in `secondary_blockers`.

---

## Logging target

No new file. The `near_miss_trace` key is appended to the EXISTING decisions.jsonl
row for that tick. The decisions.jsonl schema already supports extra keys (observed:
`filter_state`, `htf_15m_stack`, `iv_regime`, etc. were added without breaking readers).

Example row after this change:

```json
{
  "tick_id": 47,
  "date": "2026-05-07",
  "time_et": "10:51",
  "action": "HOLD_DEV",
  "bull_score": 9,
  "bear_score": 4,
  "filter_state": {"bear_blocked": [5,6,8,9,10], "bull_blocked": [6]},
  "near_miss_trace": {
    "side": "bull",
    "score": 9,
    "max_score": 11,
    "primary_blocker": 6,
    "secondary_blockers": [],
    "setup_name": null,
    "is_first_near_miss_today": true,
    "same_setup_stopped_out_today": false,
    "trigger_fired": false,
    "trigger_name": null,
    "confidence_tier": "NEAR_MISS_MED",
    "manual_review_flag": false
  }
}
```

---

## Implementation path (NOT to be done without J ratification)

1. Add a `_near_miss_trace()` helper to heartbeat (after the filter evaluation block,
   before the action-write block). The helper reads `filter_state` and computes
   the structured fields above. Pure computation — no new MCP calls.

2. In the decisions.jsonl write block, if `action in {HOLD_DEV, HOLD} AND score >= threshold`:
   merge `near_miss_trace` dict into the output row.

3. DO NOT add any LLM call for the trace. All fields are deterministic from
   `filter_state` + `bull_score`/`bear_score` + today's prior decisions.

4. Add graduated guard: `test_near_miss_trace_schema_valid` — validates all
   required fields present and typed correctly for any row with `near_miss_trace` key.

**No change to heartbeat.md required until ratification.** The spec is forward-compatible:
rows without `near_miss_trace` are valid (old format); rows with it are enriched.

---

## Why no LLM call ("auto-run heartbeat-decision-trace")

The original AC-4.2 wording implied running a separate LLM pass to "trace" the decision.
This DRAFT rejects that approach for three reasons:

1. **Cost (OP-3):** A Haiku call per near-miss = $0.0004 × ~8 near-misses/day × 252 days
   = ~$0.80/year. Negligible, BUT adds latency per tick and a new failure mode (API error
   during near-miss = trace lost). Not worth it when `filter_state` already contains
   the machine-readable blocker.

2. **L62/L68 (rate-limit pool):** Any additional Claude call during market hours competes
   with the heartbeat pool. One extra near-miss trace call per tick = up to 8 extra calls/day
   when sessions are already near rate-limit ceiling.

3. **The data is already structured.** `filter_state: {"bull_blocked": [6]}` IS the trace.
   The missing piece is just writing `primary_blocker: 6` explicitly + the boolean context
   fields (`is_first_near_miss_today`, `same_setup_stopped_out_today`). No LLM needed.

---

## Downstream consumers unlocked by this field

| Consumer | Current behavior | With `near_miss_trace` |
|----------|-----------------|----------------------|
| Weekly review | Counts near-misses by date | Clusters by `primary_blocker` — shows which filter costs most edge |
| Shadow eval (OP-11) | Ignores near-miss rows | Grades near-miss side vs next-bar truth to measure missed-edge rate |
| Kitchen seeder | Sees "HOLD_DEV count" | Sees "filter_6 blocked 18 bull entries this week" → cooks filter_6 parameter sweep |
| Dashboard | ALERT text | Badge shows primary_blocker number; J sees "6" and knows it's spread |
| L79/L80 guards | None | `trigger_name` normalized at write time — prevents suffix-match silent null |

---

## Cost estimate (OP-3)

| Item | Cost |
|------|------|
| Extra computation per near-miss tick | 0 (pure dict computation, no API call) |
| Extra tokens written to decisions.jsonl | ~200 tokens/row × 8 near-misses/day = 1,600 tokens/day |
| Storage cost | ~0.4 KB/row × 8 rows/day = 3.2 KB/day → negligible |
| LLM cost | $0 — no new LLM call |
| **Total incremental cost** | **$0/day** |

---

## Verdict

DRAFT: READY FOR RATIFICATION. Structured field spec is complete. Implementation
path is deterministic (no LLM call, no new files). Downstream consumers benefit
immediately. Cost = $0 incremental. Requires J sign-off before heartbeat.md edit.
