# An HTTP 400 wore the costume of a market condition — and cost a full trading day

**Date:** 2026-08-20
**Class:** C7 (silent success/failure) + no-silent-fallbacks. New wrinkle: the fallback did not
return fake DATA, it returned a fake **EXPLANATION**.

## What happened

`multi/core.py::fetch_option_quote` called the Alpaca snapshot endpoint with the contract as a
PATH SEGMENT: `/v1beta1/options/snapshots/{OCC}`. That form returns **HTTP 400 for every
contract**. The correct form takes it as a query param: `/v1beta1/options/snapshots?symbols={OCC}`.

The caller wrapped it in `except Exception: quote = None`. `liquidity_ok(None)` then reported
**"no two-sided quote"** — a completely plausible market condition. I read that as "the market is
closed, options don't quote" and wrote it into a handoff doc as the expected, correct behaviour
of a gate doing its job.

It ran all day on the real schedule. 20 RTH blocks, 11:37 through 14:52, market wide open, on
NVDA — one of the most liquid option chains in existence. Zero WOULD_PLACE rows.

Verified after the fix, same contract, same session: path form -> 400; query form -> bid 2.65 /
ask 2.71, **2.24% spread, 10,408 contracts of volume — it passes the 8% gate comfortably.**

## Root cause, one sentence

A bare `except` collapsed "our request was malformed" into "the venue has no quote", and the
second reading had a ready-made, believable story attached ("market's closed"), so nobody looked
further.

## Why this class is worse than fabricated data

The shop's no-silent-fallback rule is usually about fake VALUES — a default price, a stub row. This
was subtler and more dangerous: the value was honestly `None`. What got fabricated was the
**causal story**. And because "no quote outside RTH" is genuinely true most of the time, the wrong
explanation was *more* believable than the right one, and it survived being written into two
documents and one verbal review.

**Tell for this class:** an error path and a legitimate empty-state path that produce the SAME
downstream symptom. If a failure and a normal condition are indistinguishable at the call site,
the call site is wrong.

## Fix applied

1. Correct endpoint form, with the 400-vs-query-param evidence recorded in the docstring.
2. `fetch_option_quote_checked()` returns `(quote, error)` — an API/transport failure is now its
   own `quote_error` gate in the cascade and can never decay into "no quote available".

## The rule to encode

**Never let an exception path and an empty-result path converge on one downstream symptom.**
Classify at the boundary: transport/API failure, malformed request, and genuinely-absent data are
three different states and must stay three different states all the way to the ledger.

Corollary for reviews: when a plausible market-condition explanation appears for a machine
behaviour, **check it against a case where that condition is FALSE** (here: is it still "no quote"
at 11:37 on a Thursday?). A story that only ever gets tested where it happens to be true is not
tested.

**Evidence:** `automation/state/multi/shadow-ledger.jsonl` (20 RTH `liquidity_ok` blocks, all
"no two-sided quote", 11:37-14:52 on 2026-08-20); fix in `multi/core.py`.
