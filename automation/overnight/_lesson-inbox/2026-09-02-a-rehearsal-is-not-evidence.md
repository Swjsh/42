# A drill wrote into the production ledger and two safety checks read it as the real thing

**Date:** 2026-09-02 (Opus session, executing `markdown/planning/OPUS-WORK-ORDER-2026-09.md`)
**Theme:** C7 — silent success is failure. A check that a rehearsal can satisfy is not a check.

## Symptom

An early-close flatten **rehearsal** fired at 06:14 ET with an injected clock and appended
four rows to the production ledger `automation/state/logs/eod-flatten-2026-09-02.jsonl`:

```json
{"arm": "bold-2", "ts": "2026-09-02 12:45:00 ET", "dry": true, "reason": "EARLY_CLOSE",
 "outcome": "NOOP", "closed": [], "errors": [], "remaining": 0}
```

Note the timestamp: **12:45 ET, stamped by a job that ran at 06:14 ET.** Synthetic, and hours
ahead of its own write time.

Two independent consumers then read those rows as proof the EOD flatten had run. Both verified
against the real file, not reasoned about:

| consumer | what it reported | when |
|---|---|---|
| `first_live_day_review.py` | `"Core flatten confirmed flat for bold-2 (NOOP)"`, whole day **GREEN** | 11:12 ET — four hours before the real 15:52 sweep |
| `preopen_readiness.py` | `eod_reality:Gamma_EodFlattenCore GREEN {safe-3: NOOP, safe-2: NOOP, risky-1: NOOP, bold-2: NOOP}` | the **pre-open readiness verdict** (notify-only; blocks nothing by design) |

The broker calendar confirms 2026-09-02 closed at **16:00** — a normal full day. There was no
early close. The 13:00 close and the 12:45 rows were entirely drill artifacts.

## Root cause

Two defects, present independently in **both** files — which is the tell that this is a class,
not a bug:

1. `DRY_RUN` was a member of the accepted-outcomes set (`EOD_CORE_GOOD_OUTCOMES` /
   `GOOD_EOD_OUTCOMES`). A dry run flattens nothing; it cannot be a good outcome.
2. Nothing filtered `dry: true`.

In `preopen_readiness.py` the second defect is the dangerous one. That fetcher keeps the **last
row per arm**, and rows are ordered by **append, not by `ts`**. So a drill run *after* a
genuinely failed 15:52 sweep silently **displaces** the failure with a `NOOP`, and the next
morning's gate opens on a false green. The failure mode these checks exist to catch — "the
15:52 sweep did not run" — is exactly the one a leftover drill row makes report clean.

## The deeper shape

Both readers were written to the right principle. `preopen_readiness.py`'s own docstring says
absence of positive evidence is never silently GREEN. It was still wrong, because **a dry run
is absence of positive evidence wearing the costume of presence.** The principle was stated and
the data was not classified against it.

Rehearsing a safety net is good practice. Writing the rehearsal into the same ledger production
reads, in the same shape, with a synthetic timestamp, converts a drill into a forgery.

## Fix applied

- `DRY_RUN` removed from both accepted-outcome sets.
- Rehearsals excluded from evidence, but **COUNTED and named** in the human-facing reason. A
  ledger holding four rows that reports `MISSING` with no explanation is a report an operator
  argues with instead of acting on — so it reports `MISSING_ONLY_REHEARSALS` and says how many
  it ignored, on RED *and* on GREEN.
- `preopen_readiness.fetch_eod_flatten_reality` now keeps the last **real** row per arm, so a
  later drill cannot displace an earlier failure.
- Checked 08-21..09-01 before shipping: **every** genuine production row carries `dry: False`,
  so the filter costs no real evidence and cannot make the check permanently red.
- Guards: 5 new tests in `test_first_live_day_review_2026_09_02.py`, 4 in
  `test_preopen_readiness.py`. Each defect RED-proofed **independently in each file** — four
  mutations, all caught by the tests that name them.

## The rule to encode

**A rehearsal is not evidence.** Any check that reads a shared ledger must classify each row as
production or drill before grading it, and must say out loud how many it discarded. Where a
drill and production write to the same surface, the reader — not the writer — is responsible
for telling them apart, because the writer's job is to look realistic.

Corollary, and the reason this cost two files rather than one: **when a drill can write to a
shared surface, enumerate every reader of that surface before declaring the fix complete.** Two
consumers were found by grepping for readers of `eod-flatten`; one was the file that started the
investigation and one was not. Filed as `DRILLS-WRITE-INTO-PRODUCTION-LEDGERS` in
`automation/overnight/queue.md` — hardening the readers closes the false-green, but nothing
structurally stops a third reader from making the same assumption.

Related: `[[project_status_known_broken_channel_2026_08_20]]` (a report that goes nowhere
manufactures the belief something is watching) — this is the same failure with the report
arriving and being wrong, which is worse.
