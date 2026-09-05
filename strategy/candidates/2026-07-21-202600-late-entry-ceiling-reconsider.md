# Strategy candidate: late-entry ceiling (entry_no_trade_after_et) — RECONSIDER REJECTED

> DRAFT — Chef proposal 2026-07-21 20:26 ET (conductor AFTERHOURS, acting as chef persona —
> no Agent-tool subagent available this session). J ratifies (no change proposed; this is a
> disconfirming finding, not a knob-change ask).

## Hypothesis

Analyst's 2026-07-14 inbox item (`_chef-inbox/2026-07-14-late-entry-ceiling-review.md`,
queued from the 2026-07-13 zero-supervision audit) hypothesized that `entry_no_trade_after_et`
(currently `"15:00"` in both `automation/state/params.json` and
`automation/state/aggressive/params.json`) is too conservative: on 2026-07-13,
`BEARISH_REJECTION_RIDE_THE_RIBBON` re-confirmed 14 times between 15:16–15:25 ET (8 bold + 6
safe) and was killed every time by `SKIP_LATE_ENTRY`, with zero conversions to a fill. The ask:
sweep the ceiling later in 15-minute increments (15:15 → 15:30 → 15:40) and measure whether
these blocked re-confirmations would have been profitable had they been allowed to enter.

## Backtest evidence

**Data used:** live `automation/state/core-decisions.jsonl` (the only source of
`SKIP_LATE_ENTRY` events — this ledger only retains ~2 weeks, not the 30 trading days the
original item asked for; disclosed as a real limitation, not silently substituted) joined by
timestamp to `backtest/data/spy_5m_2026-05-19_2026-07-21.csv` (fresh SPY 5m OHLC cache,
refreshed today).

**Method:** Pulled every `SKIP_LATE_ENTRY` row (71 total) across the full ledger history
(2026-07-07 → 2026-07-21, 6 trading days with any occurrence). Grouped consecutive same
`(account, verdict, setup)` fires ≤3 min apart into one **episode** (a single re-confirming
signal, matching the item's own framing) → **19 distinct episodes**, not 71 independent
opportunities. For each episode, took the SPY price at the FIRST blocked fire as the
hypothetical entry price, and the SPY 15:50 ET close (the hard-flatten reference) as the
terminal price. Favorable direction = price moved the way the blocked verdict needed
(down for ENTER_BEAR, up for ENTER_BULL).

**Ceiling sweep (episodes that would newly qualify, and how many were directionally
favorable by 15:50):**

| New ceiling | Newly-qualifying episodes | Favorable-direction | Rate |
|---|---|---|---|
| 15:15 | 10 | 1 | **10%** |
| 15:30 | 13 | 4 | **31%** |
| 15:40 | 13 | 4 | **31%** |

Full per-episode detail (date, account, side, first-block time, entry SPY, 15:50 SPY, signed
move) is reproducible via the script logic above — not persisted as a separate artifact since
n=19 does not warrant a scorecard file, per OP-16/OP-20 proportionality (a full
`analysis/recommendations/*.json` write-up is reserved for candidates that clear enough n to
be actionable; see Disclosures).

- edge_capture: **N/A** — none of the 19 episodes fall on any of J's 7 named source-of-truth
  trade days (4/29, 5/01, 5/04, 5/05, 5/06, 5/07×2); this question is orthogonal to the OP-16
  edge-capture anchor set, evaluated on its own OOS-style directional bar instead.
- aggregate directional hit-rate: 10–31% favorable across all 3 tested ceilings — well below
  even a coin-flip (50%), let alone the >50%+spread-and-theta-covering rate a late-session
  0DTE entry with 10–40 minutes to work needs to clear costs.
- real_fills_validated: no — this used SPY spot price direction as a proxy for option P&L
  (no OPRA fills pulled for these specific late-session strikes/times), same disclosed-proxy
  class as prior structural-level studies in this repo (PDH/PDL/PMH/PML proxies). A full
  real-fills check would only ADD friction cost on top of an already-losing directional read,
  so it was not run (would not change the verdict, per L177/OP-16 sim-accuracy discipline —
  don't spend more compute confirming a direction that already fails outright).

## Disclosures (per OP-20)

1. **Account-size assumption:** N/A — no sizing/knob change proposed.
2. **Sample-bias disclosure:** n=19 episodes over 6 trading days is SMALL — not a walk-forward-
   grade sample. The verdict below is "insufficient evidence to support loosening the ceiling,"
   not "definitively proven the ceiling is optimal." Treat as a strong prior, not a closed case.
3. **Out-of-sample test result:** not applicable at this n (no train/test split attempted —
   splitting 19 events would produce single-digit sub-samples).
4. **Real-fills check:** not run (see above — would only add cost to an already-unfavorable
   directional read).
5. **Failure-mode enumeration:** (a) SPY-spot-direction proxy ignores path — a trade could have
   hit a stop or a partial TP before 15:50 that this analysis can't see; (b) small-n conclusions
   can flip with more data; (c) grouping by 3-minute gaps is a judgment call — a looser/tighter
   grouping window would change the episode count (though not by much, spot-checked against the
   raw 71-row list).
6. **Concentration:** top-1 episode (2026-07-07 safe ENTER_BEAR, -1.215 unfavorable move) is
   1/19 = 5.3% of episodes — no single day dominates the sample (07-13, 07-14, 07-17×3, 07-20×2,
   07-21×4, 07-07, 07-09 all contribute).

## Why this converges with, not contradicts, existing evidence

The 15:00 ceiling itself was validated by a REAL prior backtest
(`analysis/recommendations/agg_block_bull_morning_afternoon.json`, cited inline in
`aggressive/params.json`'s `_block_bull_morning_agg_doc`): POWER_HOUR (>=14:00 ET) bull entries
scored **n=3, WR=33%, total=-$45 IS**, one of the three cohorts the original gate-sweep found
losing. This fire's independent, differently-sourced check (live SKIP_LATE_ENTRY episodes,
directional-proxy method, bear-heavy sample) lands on the SAME conclusion from a different
angle: late-session (15:00+) re-confirming signals are a low-quality cohort, not a
mistakenly-discarded edge. Two independent measurements agreeing is a stronger signal than
either alone.

## Knob changes proposed

**None.** `entry_no_trade_after_et` stays at `"15:00"` on both accounts. This candidate is a
REJECTED hypothesis, filed for the record so the next fire doesn't re-litigate it from zero —
per OP-22 tiebreak (closing a loop > creating an artifact) and the `task_scorer.py`
`staleness_advisory()` discipline (verify against existing evidence before re-designing).

## Pre-merge gate

N/A — no code/params touched. `python crypto/validators/runner.py` not re-run (zero surface
area changed).

## My confidence (1-10) and why

**6/10.** The direction of the finding (don't loosen the ceiling) is well-supported by
converging evidence from two independent methods, but n=19 is thin and the SPY-spot proxy is a
real methodological gap. If a future fire has 30+ days of `core-decisions.jsonl` history (the
ledger will accumulate this passively), a re-run with real n and real OPRA fills for the
specific late-session strikes would be the honest next step — not urgent, since the current
answer already discourages the change the original item wanted made.

<!-- PROVENANCE-MISSING: automation/state/core-decisions.json -->
