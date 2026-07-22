# Strategy candidate: QQQ divergence/confluence — FIRST-PASS proxy test, INFORMATIVE (not yet fundable-for-live)

> DRAFT — Chef proposal 2026-07-21 ~20:54 ET (conductor AFTERHOURS, acting as chef persona —
> no Agent-tool subagent available this session). Engine-benefit research authoring; ships
> per OP-22/OP-25/OP-26 without J ratification (no params/doctrine/orders touched).

## Hypothesis

Chef-inbox item `_chef-inbox/2026-07-11-prospector-qqq_divergence_confluence.md`
(J+fable-2026-07-10 `CROSS-TICKER-BRAINSTORM`, "battery-ready"): label every ribbon_ride
signal with QQQ's simultaneous behavior at its own corresponding level (reclaimed/failed/
none); stratify P&L; if an agreement cohort dominates, this is a candidate for ONE scored
breadth-agreement composite feature (never a hard block). SPY is its mega-caps' proxy — a
level break unconfirmed by QQQ at its own equivalent level is the weak-break/whipsaw class
(2026-07-09 exhibit named in the brainstorm).

A prior conductor fire (2026-07-21 ~20:12-20:33 ET, chef-inbox drain pass) flagged this as
the single highest-readiness remaining item in the whole chef-inbox backlog, correctly
deferring the FULL real-fills version to "a future chef fire with its own budget." This
fire is that future fire, scoped to the cheap first-pass information test that decides
whether the expensive version is even worth funding.

## Why a proxy, not the full real-fills replay (disclosed up front)

The canonical 250-signal cohort (`_signal_cache.load_or_build_signals()`, n=250, both
directions, 2025-01-01..2026-06-18) has NO $ P&L attached without running the full
per-strike real-OPRA replay (`ribbon_ride_strike_exit_ab.py::replay_cell` — 250 signals ×
per-strike option-chain fetch/replay, a genuinely heavier pipeline). Per the
BACKTESTING-PLAYBOOK 5-stage grinder (cheap synthetic screen before expensive real-fills
validation), this fire answers the prior, cheaper question: does a QQQ agreement label
carry ANY information about SPY's own forward continuation? A negative result here means
the expensive replay isn't worth funding; a positive result is the evidence to fund it.

## Method

New script: `backtest/tools/qqq_divergence_confluence_study.py` (+ guard tests
`backtest/tests/test_qqq_divergence_confluence_study.py`, 9/9 PASS, RED-proofed by
temporarily renaming the module and confirming collection fails with the exact expected
`ModuleNotFoundError`, then restoring — **NOTE:** `git stash` was NOT used for the
RED-proof after a near-miss this fire (see Lesson filed below); rename/restore is the safe
method for an untracked new file in this shared, constantly-churning checkout).

1. **QQQ 5m bars**, same window as the signal cohort (2025-01-01..2026-06-18), fetched fresh
   via Alpaca SIP REST (69,978 bars, paginated), cached to
   `analysis/backtests/cache/qqq-5m-2025-01-01_2026-06-18.csv` — zero new external data-feed
   risk, same mechanism as the existing SPY fetch tools.
2. **QQQ's own level, no-look-ahead (C6):** for each SPY signal's `entry_ts`, compute QQQ's
   rolling 20-bar (~100 min) high/low using ONLY QQQ bars strictly BEFORE `entry_ts`. Compare
   the QQQ entry bar (first bar at/after `entry_ts`) against that prior window:
   `reclaimed` (closed through), `failed` (touched but closed back), `none` (neither).
   Guarded against look-ahead by mutating a future bar to an extreme value and confirming the
   label is byte-identical (`test_reclaim_uses_only_prior_bars_for_the_level`).
3. **Outcome proxy:** direction-aligned SPY spot return over the next 30 minutes from
   `entry_ts` (positive = the SPY signal kept going the intended way). **NOT a $ P&L, NOT a
   real fill** — a MODELED spot-return information-test proxy, same disclosed-proxy class as
   the late-entry-ceiling study earlier tonight and the PDH/PDL/PMH/PML structural-level
   studies already in this repo.

## Results (`analysis/recommendations/qqq-divergence-confluence-study.json`)

| QQQ label | n | mean aligned return | median | % positive |
|---|---|---|---|---|
| reclaimed | 21 | **+1.08** | +0.77 | 81.0% |
| failed | 27 | +0.55 | +0.69 | 70.4% |
| none | 202 | +0.07 | -0.02 | 48.5% |

Reclaimed-vs-other mean spread: **+0.96** (SPY points, aligned). Verdict:
**QQQ_AGREEMENT_INFORMATIVE**.

By direction: bull n=59 (8 reclaimed / 12 failed / 39 none); bear n=191 (13 reclaimed / 15
failed / 163 none). All 250 signals had usable QQQ+SPY bars (0 dropped).

## Disclosures (per OP-20)

1. **Account-size assumption:** N/A — no sizing/knob change proposed; this is a proxy
   information test, not a wiring proposal.
2. **Sample-bias disclosure:** `reclaimed` (n=21) and `failed` (n=27) both clear the
   `probe_stats.INCONCLUSIVE_MIN_N=10` floor but are still SMALL relative to `none` (n=202) —
   treat the magnitude as a directional prior, not a certified edge size.
3. **Confound not yet ruled out (the honest caveat):** `failed` (n=27, mean +0.55) is ALSO
   well above `none` (mean +0.07), despite QQQ explicitly NOT confirming the break in that
   cohort. This suggests the effect may partly reflect "QQQ was active/volatile enough to
   even reach the level" (a general participation/trend-day proxy) rather than pure directional
   *confirmation* specifically. A trend-day control (e.g., stratify by realized volatility or
   VIX regime at entry) is needed before concluding this is a clean confirmation signal and
   not a volatility-regime proxy in disguise — named here as the FIRST thing the funded
   real-fills follow-up must check, not silently absorbed into the "informative" verdict.
4. **Out-of-sample test:** not run — this is a single-pass information test on the full
   window, not a train/test split. The eventual real-fills replay must carry its own OOS/WF
   split per the standard OP-11/OP-16 bar before any wiring proposal.
5. **Real-fills check:** explicitly NOT run this fire (that's the next, funded step — see
   "Next step" below). This result is NOT eligible for `conductor-proposals.jsonl` on its own.
6. **Concentration:** not computed — the outcome unit here is a spot-return proxy, not a $
   P&L series, so day-concentration (`probe_stats.day_concentration`) doesn't apply cleanly;
   the real-fills follow-up should compute it on actual $ P&L.

## Next step (named, not executed this fire — scope discipline)

Verdict is `QQQ_AGREEMENT_INFORMATIVE` → **fund the full real-fills replay**: reuse
`ribbon_ride_strike_exit_ab.py`'s per-strike SS-B replay machinery, stratified by this
fire's `qqq_label` (join on `entry_ts`), with the confound check from disclosure #3 run
FIRST (does the reclaimed-vs-none spread survive controlling for realized volatility at
entry?). Only if that clears the standard OP-11/OP-16 bar (OOS positive AND WF>=0.70 AND
sub_window_stable AND anchor_no_regression) does a wiring proposal (a scored
breadth-agreement feature, never a hard block, per the original finding's own framing)
reach `conductor-proposals.jsonl`.

## Knob changes proposed

**None.** This is a research/authoring artifact — zero trading-path files touched
(`params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code untouched).

## Pre-merge gate

`python -m pytest backtest/tests/test_qqq_divergence_confluence_study.py -q` → 9/9 PASS.
`python crypto/validators/runner.py` not re-run (zero engine/gym surface changed — pure
research tool + analysis output).

## My confidence (1-10) and why

**6/10.** The raw spread is real and the sample clears the n>=10 floor per stratum, but
disclosure #3's confound (reclaimed AND failed both beat none — may be a trend-day/
volatility proxy, not pure QQQ-specific confirmation) is a genuine open question the funded
follow-up must resolve before this graduates past "worth funding" to "worth wiring."
