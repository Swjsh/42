# Lesson candidate: multi-tier LLM fallback gates must check output-parseability, not just `ok=True`+non-empty

**Date:** 2026-08-20
**Source:** conductor fire, STATUS.md entry `[2026-08-20 20:36 ET] conductor: OK — fixed kitchen_reviewer masked-exit flapping`, commit `84ccfde5`.

## Symptom

`run-kitchen-reviewer.ps1` (Kitchen R&D loop, fires every 2h) exited 1 on 3 of
9 fires in a single day (33%). Task Scheduler's `LastTaskResult` couldn't
surface it (the outer wscript hop is fire-and-forget) — only caught by
`self_check.py` grepping the run-ps1-hidden log for non-zero exits, which
then showed up as engine-health `RUN-PS1-HIDDEN MASKED EXIT` and a
`desk_allocator.py` "SPY 0DTE desk BROKEN (self-check DEGRADED)" flag that
was actually about the Kitchen, not the trading desk.

## Root cause

`kitchen_reviewer.py` had a 2-stage fallback: try a free "pool" model first,
fall back to a 4-tier `MODEL_LADDER` only `if not (result and result.get("ok")
and content.strip())`. The primary pool model (nvidia/nemotron, a *reasoning*
model) would sometimes spend its whole `max_tokens` budget on chain-of-thought
prose ("Let's go through each candidate one by one...") before ever reaching
the required JSON object — confirmed via saved raw dumps
(`reviewer-bad-response-20260820T084643.txt`, 41.8KB, zero `{` ever reached).
That response is `ok=True` + non-empty, so it passed the "usable" gate and the
ladder (which has 2 non-reasoning free models specifically for this case) was
never tried. The fire just aborted downstream when JSON extraction failed.

## Generalizable lesson

**Any pipeline that gates "did this model call succeed" on transport-level
success (`ok=True`, non-empty string, HTTP 200) instead of on "does the
output satisfy the contract the caller actually needs" will silently skip
its own fallback tiers exactly when they're needed most** — a reasoning
model returning `ok=True` with unusable prose is a MORE dangerous failure
mode than an outright API error, because API errors already trigger the
fallback; parseable-looking success does not. Any multi-tier LLM ladder in
this codebase (chef_nemotron's own `_call_with_ladder`, swarm_client's role
routing, any future reviewer/triager) should be audited for the same gap:
does "usable" mean "the caller's parser can consume it", or just "the
transport didn't error"?

## Fix shipped

Gate `usable` on `_extract_json_object(content)` succeeding (not just
`ok`+non-empty) for both the pool result and each ladder tier, so a garbled
response from one model falls through to the next. Guard:
`backtest/tests/test_kitchen_reviewer_ladder_fallback_2026_08_20.py`.

## Suggested L## text (for lesson-author)

Add to C14 (Dead/translated-but-unapplied knobs) or a new bucket: a
multi-tier model fallback whose "success" gate is transport-only (ok=True +
non-empty) rather than contract-level (output parses per the caller's
schema) will never actually fall back on the most common LLM failure mode —
a well-formed-but-wrong response from a reasoning model that burned its
token budget on chain-of-thought instead of the requested format.
