# G11 Level-Memory Wire — A/B Replay Scorecard

**Queue item:** `G11-LEVEL-MEMORY-AB-REPLAY` (`automation/overnight/queue.md`, 2026-07-09 after-hours). **Pre-registration:** [`prereg-level-memory-wire-2026-07-15.json`](prereg-level-memory-wire-2026-07-15.json) (frozen + committed before this run). **Scorecard:** [`level-memory-wire.json`](level-memory-wire.json). **Runner:** `backtest/tools/level_memory_wire_ab.py`.

## Verdict: NEGATIVE_INSUFFICIENT_N — flag stays ON

The wire trends negative in the modeled window (n=3 changed-behavior trades, combined P&L −$489.50) but n is **far below the 15-evidence floor** the pre-registration set specifically to prevent a 2-3-trade sample from driving a production change. Per the pre-reg's own kill criteria, this is reported as `NEGATIVE_INSUFFICIENT_N`, not `NEGATIVE` — **`level_memory_live_merge` stays `true`.**

## What was tested

The backtest engine's own level detection (`backtest/lib/levels.py`) has **zero notion of level_memory** — confirmed by code read, it derives levels purely from OHLC price structure. So CONTROL (the vanilla backtest) is the correct proxy for "wire OFF," and TREATMENT unions the *same* memory-merge formula the live wire uses (`refresh_levels_intraday.py#_merge_memory_levels`: nearest-6 within 1.5% of spot, `memory_score>=60`/`tier==Active`) via a new additive `memory_levels_by_day` kwarg on `_detect_from_history` — real production trigger logic (`filters.py`, unmodified), not a reimplementation.

- **Window scored:** 2026-06-05 → 2026-07-14 (26 trading days), real-fills OPRA pricing, live Safe `params.json` config, ATM strike (live-truth override — `params.json`'s per-tier ladder is vestigial on the live core path per the 2026-07-11 strike-tier reconciliation).
- **Lookback buffer:** 2026-05-19 → 2026-06-04 feeds the 10-trading-day memory lookback for every scored day — no look-ahead.
- **OPRA cache:** backfilled 4 missing days (07-09/07-10/07-13/07-14, 88 contracts, 0 errors) so the whole window replays on real fills, not BS fallback.

## Headline numbers

| Bucket | n | P&L |
|---|---|---|
| CONTROL trades (total) | 28 | — |
| TREATMENT trades (total) | 26 | — |
| **(a) Participation added** (new entries only the wire enables) | 2 | **−$489.50** |
| (b) Removed (control-only, preempted by cascading day-state) | 4 | −$289.64 *(reported, not counted toward verdict)* |
| **(c) Shared-signal behavior changed** (same bar, different level attribution) | 1 | $0.00 |
| **Combined (a+c) — the verdict metric** | **3** | **−$489.50** |
| Shared, unchanged | 23 | — |

**Concentration:** both participation-added trades are losers (top-1 = 51.5%, top-3 = 100% of the bucket's P&L — n=2, so top-3=top-2=all of it).

## Mechanism confirmed

Both participation-added trades carry a `confluence` trigger they wouldn't otherwise have: a memory-merged level entering `multi_day_levels` satisfies `detect_confluence`'s proximity check against an existing `level_rejection`. This is the real, working mechanism — not noise. Both were bear/put SUPER-ish trades that hit `EXIT_ALL_PREMIUM_STOP`.

The "removed" bucket (b) is a genuine **cascading day-state effect**, exactly what the pre-registration flagged as a possibility: adding a memory level can change *which* bar fires first, consuming the day's one-trade slot and preempting a later trade. One of the four removed trades was a `BS_FALLBACK` winner (+$407.86, real OPRA data was missing for that specific 06-11 strike). Net, the removed cohort itself was already money-losing in CONTROL (−$289.64) — losing access to it is roughly a wash, which is why it's disclosed but not folded into the kill metric (per the frozen pre-reg).

## Live cross-check (the 3 real wire-live sessions: 07-09, 07-10, 07-14)

36 real `ENTER_*` verdicts logged for the Safe account across those 3 sessions. **3 rows matched a memory-sourced level** — but all 3 are the *same* persisting signal logged on 3 consecutive 1-minute heartbeat ticks (10:36:03 / 10:37:03 / 10:38:03 ET, 07-14, `trigger_level_exact=751.75` vs memory candidate `751.81`), i.e. **one real episode**, not three.

That episode (`BULLISH_RECLAIM_RIDE_THE_RIBBON`, quality tier SUPER, passed scoring + all 15 entry gates) was blocked twice by `VETOED_BY_MODELS` (free-model veto) and then by `RISK_DENY_PDT` ("7 day-trades in 5d at equity $1,747 < $25,000"). **No order was ever placed.**

So the wire's entire real-world footprint in its first 3 live sessions: contributed to one signal reaching SUPER tier, zero fills, zero real P&L. Unrelated downstream gates (model veto, then PDT) decided the actual outcome, not the wire.

## Decision

- **Flag:** `level_memory_live_merge` stays `true` in `automation/state/params.json` — insufficient evidence to invoke the queue item's revert clause.
- **Revert clause on file** (queue item, pre-authorized): "revert = flip `level_memory_live_merge:false` if negative." Read against the pre-registration's evidence floor, a 3-trade sample doesn't meet the bar for that revert — this is a **deliberate non-application** of an available revert, not an oversight.
- **Standing note for the next review:** the wire has now produced a real, mechanistically-confirmed but negative-leaning signal (2 losing participation trades in the counterfactual, 1 real SUPER-tier episode that never filled). Re-run this same frozen methodology once either (a) the live wire crosses ~15 real touched decisions, or (b) a longer counterfactual window is scored — whichever comes first — rather than waiting indefinitely on an inert instrument.
- **C14 wiring guard added:** `backtest/tests/test_graduated_guards.py::test_level_memory_live_merge_key_present_and_boolean` asserts live `params.json` carries `level_memory_live_merge` as a present boolean (closes `G11-C14-WIRING-GUARD`).

## Deviations disclosed (per pre-reg)

- LevelSet is cached **once per day** by the orchestrator (pre-existing perf optimization) — the memory-merge spot-band uses the day's *opening* price, not a continuously 5-min-refreshed spot like the live wire. This is a conservative simplification (understates participation, not overstates it).
- The memory candidate set itself is computed once per day (via prior-close history), matching multi-day memory levels' slow-moving nature.
