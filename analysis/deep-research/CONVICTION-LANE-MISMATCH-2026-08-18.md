# Why conviction scores our winners zero: it was built for a book we don't trade

> Session finding, 2026-08-18 evening, during J's alignment review. Derived from
> `automation/state/core-decisions.jsonl` (28,879 rows / 42 days, 2026-06-25 .. 2026-08-18)
> and the 206 live conviction rows on disk. Conviction remains **DISARMED**; nothing here
> changed engine behaviour.

## VERDICT

**The conviction ratchet keys its highest-weight component on a named horizontal level. The
filter stack selects almost perfectly AGAINST level-tied bear entries. So the gate that stands
between us and equity-scaled sizing is structurally unable to score the trades we actually
take.**

This is not a bug in conviction and not a bug in the filters. It is a **lane mismatch**: two
correctly-working subsystems built for different books.

## The measurement

Bear side, whole decision log:

| stage | n | level-tied | trendline-tied |
|---|---:|---:|---:|
| **detections** (any bear trigger fired) | 5,349 | **4,642 (86.8%)** | 1,253 (23.4%) |
| ENTER_BEAR verdicts (incl. gate-blocked) | 478 | 38 (7.9%) | **453 (94.8%)** |
| **actually PLACED puts** | 35 | **6 (17.1%)** | **30 (85.7%)** |

Read the first and last rows together. **We detect a level-tied bear setup 86.8% of the time
and fill one 17.1% of the time.** The trendline lane is detected 3.7× less often and fills 5×
more often. Somewhere between detection and fill, the stack inverts its own input distribution.

The mechanism is already documented from the other end: the trendline-only shape **waives
filters 5/8/9** (`filters.py:1662-1672`), and filter 8 requires VIX > 17.30 *and rising*. At the
mid-VIX levels where this book lives most days, the ordinary level-tied bear machinery is
structurally off and only the waiver lane can fire. The 08-17 winner entered exactly this way.

## What that does to conviction

`trigger_level_exact` — the anchor C1 scores against — across the 206 live conviction rows:

| side | rows | `trigger_level_exact` set |
|---|---:|---:|
| CALL (C) | 68 | **68 (100%)** |
| PUT (P) | 138 | **0 (0%)** |

Not once, on any put, on any of the six days conviction has been scoring. And puts are where
this book's money comes from — both live winners were puts.

⚠️ **Do not read this as "the bear side cannot produce a level."** It can and does — bear
`level_rejection` is the single most common trigger in the entire log (4,472 firings, more than
bull `level_reclaim`'s 3,636). The level is absent *at entry* because the entries that survive
the filters are the ones that came in through the trendline waiver.

## Live component health — the rest of the ratchet is thinner than it looks

All 206 rows, split at the documented 2026-08-14 C4/C5 fix boundary:

| component | pre-fix (n=102) | post-fix (n=104) | note |
|---|---|---|---|
| `named_level` | 68 fire | **0 fire** | sample flipped to all-put; see above |
| `elite_trigger` | 68 fire | **0 fire** | same cause |
| `fresh_test` | 32 fire | **0 fire** | same cause |
| `multi_day_memory` | 0 fire | 0 fire | **never fired, 0/206** |
| `range_extreme` | degraded 102/102 | 0 fire (no longer degraded) | 08-14 fix worked — `range_position` now writes 100/104 — but the scoring key still never pays |
| `structure_agreement` | degraded 102/102 | **degraded 77/104 (74%)** | 08-14 fix only partially landed |
| `zone_stack` | 10 fire | 0 fire | |

**The 08-14 C4 fix is confirmed genuinely effective** — `range_extreme` went from degraded on
every single row to degraded on none, and `range_position` (written only on the non-degraded
branch) now appears on 100/104. That fix did what its commit said.

**The C5 structure fix did not fully land**: `structure` is still degraded on 74% of post-fix
rows. An independent replay agent found the same class of defect in reconstruction — a naive ET
timestamp raising *inside* a fail-open `except`, which looks identical to a genuine "no signal"
day. Whether the live path fails for the same reason is **not yet established** and is the next
thing to check.

## Why this matters more than the trendline variant I shipped today

Conviction v2 (the trendline anchor, shadow-only) was aimed at exactly this blindness, and the
aim was right. But the historical replay showed its quality bar (respects ≥ 20, violations ≤ 6)
fires on **32/32** trendline-triggered round trips — winners and losers alike — because
`_match_trendline` has **no distance cap** and will credit any qualifying line up to $1.10 from
spot. All of v2's apparent discrimination came from a separate $0.60 proximity check, which is a
re-derivation of the already-known proximity signal, not new evidence.

So the honest state of conviction tonight:

- **v0** cannot score the lane we trade. Verified, structural, 0/138 puts.
- **v2** can score that lane but does not rank it. Verified, 32/32 fires.
- Three of seven components (`multi_day_memory`, `range_extreme`, `zone_stack`) have paid out
  ~never across 206 rows.
- **The gate to equity-scaled sizing is therefore not "unvalidated." It is not yet measurable.**

## What follows (nothing is armed; nothing here is a recommendation to arm)

1. **Fix the C5 structure degradation first.** It is the one component still failing for a
   mechanical reason rather than a design reason, and 74% degradation makes the whole score
   unreadable.
2. **Give `_match_trendline` a distance cap** so C1-by-trendline means "at this line," matching
   what C1-by-level already means. Shadow-only change; cheap; testable.
3. **Then re-ask the discrimination question** — and only then. Asking it now measures noise.
4. **The lane mismatch itself is the strategic finding.** Either conviction learns to score the
   waiver lane, or the filter stack stops selecting so hard for it. Those are different projects
   with different evidence bars, and picking between them is J's call, not a code change.

## Honest limits of this analysis

- `n=35` actually-placed puts is a small sample; the 478-verdict figure is directionally
  consistent but includes gate-blocked verdicts that never became orders.
- 261 of the 478 ENTER_BEAR rows predate the 2026-07-27 trigger-schema change and were read
  from the legacy top-level `triggers` field; 217 used `bear_triggers_raw`. Both were counted
  with the same predicate.
- Conviction has only been scoring since 2026-08-13. Six days is a small window and the
  pre/post split is 2 days vs 2 days — component-fire rates will move.
- I did not verify whether the live C5 path fails for the same timestamp reason the replay
  harness did. That is stated as unknown above, not assumed.
