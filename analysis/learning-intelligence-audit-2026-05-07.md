# Audit — Learning & Intelligence Pillars

**Filed:** 2026-05-07 (post P0+P1+P2 dial-in)
**Scope:** How does Gamma grade trades, mistakes, decisions, and hypotheses each day? What's actually benchmarked? Where does the journal turn into a recommendation?
**Constraint per J:** *No strategy changes without J's approval. This audit produces suggestions only — recommendations live here, ratification lives with J on Monday.*

---

## What's deployed today (after P0/P1/P2)

The learning loop currently looks like this:

```
Premarket  →  writes today-bias.falsifiable_hypothesis (claim/window/invalidation)
                + iv_regime + monday_watch (Mon only)
                + reads dashboard-dialogue.ticker_speech (yesterday's hint)

Heartbeat  →  emits ACTION per tick
                writes loop-state, current-position, dashboard-dialogue
                appends rows to skipped-setups.csv when score ≥ threshold
                appends entry/exit rows to trades.csv with 34 columns
                                (setup_quality, fill_quality, trade_grade,
                                 followed_rules, gamma_recommended, j_override,
                                 hold_minutes, slippage_cents, tod_bucket,
                                 iv_regime, delta_at_entry, iv_at_entry, etc.)

EOD        →  grades hypothesis (PASS/FAIL/PARTIAL/UNTESTED)
                appends row to hypothesis-grades.jsonl
                detects rule breaks → rule-breaks.jsonl + mistakes.md auto-flags
                writes structured EOD reflection block to journal
                recomputes setup-performance.json (cumulative + by_iv_regime + by_tod_bucket)

Daily Review → writes daily-review-{date}.json (graded predictions array)
                replay-screenshots each trigger event into journal/replays/
                writes "tomorrow's hint" to dashboard-dialogue.ticker_speech
                writes Daily Review markdown section to journal

Weekly Review → reads everything above for the week
                  writes analysis/{YYYY-Www}.md with hit rate, expectancy,
                    mistake patterns, deployment threshold check,
                    promote/demote recommendations, tunings to consider
                  updates ticker_speech for Monday premarket
```

That's a real pipeline. The signal-capture layer is in place. What this audit examines: **is the grading + benchmarking + suggestion-generating layer actually intelligent, or just busy?**

---

## Pillar 1 — Trade Grading

### What's measured

Per trade row in `trades.csv`:

| Column | Type | Who fills | Honesty |
|---|---|---|---|
| `setup_quality` | CORRECT/WRONG/PARTIAL | EOD prompt | Subjective; no rubric |
| `trade_grade` | EXCELLENT/GOOD/OKAY/POOR | EOD prompt | Subjective; no rubric |
| `followed_rules` | Y/N/partial | EOD prompt | Decent — rules are explicit |
| `dollar_pnl`, `r_multiple` | computed | heartbeat | Hard numbers |
| `slippage_cents`, `exit_slippage_cents` | computed | heartbeat | Hard numbers |
| `hold_minutes` | computed | heartbeat | Hard number |

### Gaps

1. **Subjective grades have no rubric.** "EXCELLENT" vs "GOOD" is whatever Gamma decides at EOD. Two runs of the EOD prompt on the same trade might disagree. This is the same class of softness that P0 fixed for the heartbeat filters — but the EOD's grading still relies on adjective-level reasoning.

2. **No counterfactual analysis.** A winning trade with a sloppy exit might have left $400 on the table. A losing trade might have won if held 2 more bars. We don't compute "what would have happened if I'd held to time stop?" or "what would the runner have done if exited 5 min later?" The replay screenshots in P2 *show* the trigger, but no automated "post-trade walk-forward" computes what an alternative exit would have made.

3. **No archetype-match score.** The 5/4 trade is the canonical example (EXCELLENT, +86%). The 5/1 is a known anticipation flaw (POOR, +72%). Every new trade should be scored against the playbook's canonical archetypes — "this looks 0.85-similar to 5/4, 0.30-similar to 5/1." The system has the trade rows but no similarity computation.

4. **No "luck factor" decomposition.** A trade can win on:
   - Right setup + right execution + favorable market = SKILL
   - Right setup + right execution + market moved further than typical = SKILL + LUCK
   - Right setup + sloppy execution + market handed it to you = LUCK
   - Wrong setup + lucky entry + reversal = PURE LUCK
   - The current `trade_grade` muddles these. We need a column like `tape_assistance: ["normal", "favorable", "exceptional"]` based on the underlying SPY move's distance vs typical move size in the same IV regime.

5. **`gamma_recommended` and `j_override` are columns but no grading logic uses them.** When `gamma_recommended=N AND j_override=Y AND outcome=win`, that's J's gut beating the system. When `gamma_recommended=Y AND j_override=N AND outcome=loss`, that's a Gamma-driven loss. These are different lessons. Not currently surfaced.

### Suggestions (J's approval required to implement)

> **S1.1 — Trade grading rubric.** Define a checklist that computes `trade_grade` from objective inputs rather than feel:
> - Did the entry happen within 1 bar of the trigger? (yes = +1)
> - Did TP1 fire as designed? (yes = +1)
> - Did the runner exit on a documented signal (ribbon retest, bounce signature, time stop)? (yes = +1)
> - Was max adverse excursion < 30% of entry premium? (yes = +1)
> - Did slippage at entry < $0.05? (yes = +1)
> - Score 5 = EXCELLENT, 4 = GOOD, 2-3 = OKAY, 0-1 = POOR. Adjective output preserved; arithmetic input added.
>
> *J ratifies the checklist. EOD computes the score from heartbeat-recorded data. No subjectivity in the math.*

> **S1.2 — Counterfactual exit analysis.** Add EOD step: for every closed trade, replay the position's chart from entry to 15:50 ET (in steps), compute `would_have_made_if_held_to_time_stop` and `would_have_made_if_exited_at_high_water`. Append two columns to trades.csv: `cf_time_stop_pnl`, `cf_high_water_pnl`. These are NOT used to second-guess the actual exit — they're learning data for the weekly review's "exit timing" pattern detection.

> **S1.3 — Archetype similarity score.** New column `archetype_match: { closest: "5/4", similarity: 0.85, second: "5/1", similarity: 0.32 }` computed at EOD by comparing the trade's signature features (ribbon spread at entry, vol on trigger bar, trigger type, hold duration) to the historical examples in playbook.md. Setups whose archetype-match drifts toward "5/1 anticipation" pattern over time = warning to J that drift is happening.

> **S1.4 — Tape assistance tag.** Compute the day's SPY move from open-to-trade-direction-extreme as a percentile against last 30 days' moves. Tag the trade `tape_assistance: ["dry", "normal", "favorable", "exceptional"]`. A win in "dry" tape = stronger evidence. A win in "exceptional" tape = needs caveat. Surfaces in setup-performance.json.

---

## Pillar 2 — Mistake Learning

### What's measured

Each EOD writes `rule-breaks.jsonl` with `{date, rule_id, trade_row, severity, what_happened, fix_proposal}` and appends auto-flag bullets to `mistakes.md`. Weekly review clusters by rule_id and tags `**REPEATING**` if 2× this week or 3× across 4 weeks. Monday premarket reads top pattern + 7-day watchlist.

### Gaps

1. **No mistake → outcome linkage.** When a rule break is detected, we don't compute its cost. "Anticipation entry on 5/1" cost J nothing in P&L (still won) but cost +194% return that a clean entry would have made. The fix_proposal addresses the rule but doesn't surface the magnitude. A repeating mistake that's CHEAP is different from a repeating mistake that's EXPENSIVE.

2. **No "would-have-fired-anyway" check.** When the system blocks an entry on a rule (e.g., `SKIP_LIQUIDITY` because spread > 8¢), and the would-be-entry would have won big, that's evidence the rule may be too tight. The skipped-setups.csv captures the skip but doesn't grade the counterfactual cost.

3. **No "mistake half-life" tracking.** If J broke "wait for trigger" 3 times in week 1, then 1 time in week 2, then 0 in week 3, the mistake is dying out — that's good. But if it spikes back in week 4, that's a relapse. The weekly review only looks at "this week" + "last 4 weeks aggregated." It doesn't show the rate of decay.

4. **Auto-flags are one-liners; narrative entries are rare.** The auto-flag format `**<rule_id>** (severity) — what_happened. Trade row: <#>. Fix: <fix>` is good for reading the dashboard but doesn't capture the *why* (emotional driver, context, time pressure). The 2026-05-01 narrative entry in `mistakes.md` is rich precisely because J wrote it. The system can't write the narrative; it can only flag for J to write it on Monday.

5. **No mistake clustering by trade family.** A setup might have a "stop too tight" pattern, a different setup might have a "ribbon read too aggressive" pattern. Currently rule_id clusters globally, not per-setup. We can't see "BEARISH_REJECTION_RIDE_THE_RIBBON has 3 anticipation entries; BULLISH_RECLAIM has 0" without manual reading.

### Suggestions

> **S2.1 — Mistake cost capture.** Augment `rule-breaks.jsonl` with `cost_estimate_dollars` (computed at EOD from actual outcome vs counterfactual clean-entry outcome) and `cost_estimate_method` ("counterfactual" or "actual"). Weekly review then sorts mistake patterns by cumulative cost, not just count. The most-frequent isn't always the most-expensive.

> **S2.2 — Skip cost log.** Augment `skipped-setups.csv` with `cf_30min_pnl_estimate` (computed at next EOD by walking the chart 30 min forward from the skip and computing what a 3-contract ATM entry would have made/lost). After 20 skips, weekly review shows: "of 20 skips, 12 would-have-lost (filter saved you), 8 would-have-won (filter blocked profit). Estimated saved: $X. Estimated forgone: $Y." If forgone > saved, the filter is too tight — a tuning recommendation fires.

> **S2.3 — Mistake half-life tracking.** Weekly review adds a `## Mistake decay` section per repeating rule_id. Shows count for each of the last 4 weeks (week-over-week). Up arrow = relapsing, flat = persistent, down arrow = improving. Visible in one glance.

> **S2.4 — Per-setup mistake clusters.** Cluster `rule-breaks.jsonl` by `(setup_name, rule_id)` instead of just `rule_id`. Surface in weekly review § 3 and in setup-performance.json's per-setup block.

> **S2.5 — Monday narrative prompt.** Premarket on Monday, after surfacing the top pattern and watchlist, asks J directly (via journal): *"Top pattern this week is `<rule_id>` (×N). The auto-flags say what happened — but do you want to write the narrative behind it before today's session? Open `mistakes.md` and add a `## YYYY-MM-DD — <pattern>` section if you do."* This is a NUDGE, not an automation. The narrative discipline can't be automated, only invited.

---

## Pillar 3 — Decision Grading (the biggest gap)

### What's measured today

Almost nothing. We grade *trades* (an aggregate of many decisions) and *hypotheses* (the morning prediction). We don't grade the individual decisions that made up the trade or the day.

### Why this is the biggest gap

A single trade has 4+ distinct decisions:

1. **Entry decision** — was this the right bar? Right strike? Right size?
2. **Hold decision** — every 3-min tick that didn't exit IS a hold decision. 30-bar trades = 30 hold decisions.
3. **Exit decision** — TP1, runner exit, stop, time stop. Was it triggered cleanly or anticipated?
4. **Re-entry / second-trigger decision** — if a setup re-fires, did we honor first-entry-only or re-engage?

A skip is also a decision:

5. **Skip decision** — at score 9/11 with one filter blocked, should we have entered with reduced size?

A trade can win with poor decisions ("got lucky") or lose with good decisions ("the regime didn't cooperate"). Right now, the only thing we grade is the aggregate P&L and a vibe-based `trade_grade`.

### Gaps

1. **No per-tick grading of the management branch.** The position branch fires every 3 min while a position is open. Each tick the heartbeat decides "hold or exit." We log the tick but don't grade the decision. If the runner held through 5 hold-decisions and exited on the 6th, we don't ask: were the 5 holds correct given what was visible at each tick?

2. **No skip-decision grading.** Skip rows are captured (filter, score, reason) but not graded as "right skip" vs "wrong skip" by EOD. After 10 skips with `would_have_won` data, we'd have a real signal: are our filters skipping mostly losers (good) or mostly winners (bad)?

3. **No entry-timing precision score.** A trigger fires at 10:27 close. The next bar opens 10:30. Did we enter on the 10:30 open, mid-bar, or wait until 10:33? The slippage column captures price; it doesn't capture timing precision.

4. **No "consistency" measurement.** Did J / Gamma make the same decision on similar setups across the week? If 3 BEARISH triggers fired this week and we entered 2 of them, what differentiated the skip from the entries? Is the differentiation principled (a filter said no) or arbitrary (we just didn't take it)?

### Suggestions

> **S3.1 — Decision-events table.** New file `analysis/decisions.jsonl`. Heartbeat appends one row per ACTION (every tick that emits ENTER, HOLD, HOLD_DEV, EXIT_*, SKIP_*). Schema: `{tick_id, date, time_et, action, position_status, bull_score, bear_score, filter_state, reason}`. EOD grades each non-trivial decision (anything except plain HOLD with no setup) into `decision_grade: ["correct", "wrong", "ambiguous"]` based on subsequent 30-min outcome. After 200 decisions, we can compute Gamma's decision hit rate independently of trade hit rate.

> **S3.2 — Skip cost retro at EOD.** EOD walks today's `skipped-setups.csv`, computes the 30-min-forward outcome for each skip, writes `would_have_outcome: ["win", "loss", "flat"]` and `would_have_pnl_estimate`. Weekly review surfaces: "X skips this week — Y would have won (estimated $Z forgone), Z would have lost (filter saved you $A)." If forgone > saved by ≥ 2× over 20+ skips, a tuning recommendation fires.

> **S3.3 — Hold-quality score per trade.** EOD walks the position-branch ticks during the trade. For each hold tick, compute "if I'd exited here, P&L would be X." The trade's hold-quality score = how often the actual exit P&L beat each interim hold's P&L. A score of 0.95 = exited near the top. A score of 0.40 = exited well before the optimum. New trades.csv column: `hold_quality_pct`.

> **S3.4 — Entry timing precision.** Augment trades.csv: `bars_after_trigger` (how many 5-min bars elapsed between trigger close and our entry — should be 0 or 1; >1 = anticipation or chase) and `entry_relative_to_bar` ("at_close", "intra_bar", "next_open", "later").

> **S3.5 — Decision consistency report.** Weekly review section: "this week, BEARISH_REJECTION fired N times. We entered M, skipped K. Differentiation: <list of which filter blocked each skip>. Consistency score = M / N if no skipped trade had a hard-block reason; lower if we skipped on subjective grounds."

---

## Pillar 4 — Hypothesis Grading

### What's measured

`hypothesis-grades.jsonl` — one row per day, fields: `date`, `claim`, `trigger_window`, `invalidation`, `outcome` (PASS/FAIL/PARTIAL/UNTESTED), `why`. Weekly review aggregates into a hit rate.

The schema gain from P0 (claim/window/invalidation as required fields) is real — vague hypotheses can't slip through anymore.

### Gaps

1. **One claim per day is too coarse.** The morning bias_note implicitly contains 3-5 predictions: "725 holds as resistance," "ribbon stays bearish-stacked through morning," "VIX rises through 17.30 if the setup fires," "no setup fires before 10:30." Currently we grade ONE — the falsifiable_hypothesis. The other implicit predictions are ungraded.

2. **No calibration tracking.** If J/Gamma writes "85% confident this level holds" 20 times, and the level holds 12/20 times = 60% reality, we're systematically overconfident. We don't track `claim_confidence` so we can't compute calibration. (See: forecasting.research; Tetlock's superforecasters always tracked their own calibration.)

3. **No specificity score.** "Bias bearish, hunting BEARISH_REJECTION_RIDE_THE_RIBBON" is a hypothesis. So is "725.04 holds as resistance on first test today, fails if SPY closes a 5-min bar above 725.20." Both can be PASS. The second is *enormously* more useful. We don't differentiate.

4. **No novelty tracking.** If today's hypothesis is structurally identical to yesterday's ("levels XYZ, bias bearish") and yesterday's was wrong, we don't note that we're repeating a failed thesis.

5. **No PARTIAL granularity.** PARTIAL is a single bucket. But "level held at the right time but gave way later in the day" and "level held but the implied entry never fired" are different partials. We collapse them.

### Suggestions

> **S4.1 — Multiple claims per day.** Premarket writes `falsifiable_predictions: [...]` (array, target 3-5 items per day) instead of a single `falsifiable_hypothesis`. Each prediction has the same {claim, window, invalidation} schema. EOD grades each independently. Hit rate then computed across the array, not just one row. The `falsifiable_hypothesis` field stays as the "primary claim" for back-compat with existing scripts.

> **S4.2 — Confidence + calibration.** Each prediction in the array gets a `confidence: 0.0-1.0` field at write time. Weekly review computes calibration buckets: predictions with conf 0.55-0.65 should hit ~60% over time. After 50 predictions, plot calibration; flag systematic over/under-confidence as a meta-pattern.

> **S4.3 — Specificity score.** Each prediction gets a `specificity` 0-1 score from premarket's self-validate step:
> - Contains a number? +0.4
> - Contains a bar-close or time bound? +0.3
> - Contains an explicit invalidation rule that references a number? +0.3
> Predictions with specificity < 0.7 fail self-validate (already enforced for invalidation field; this extends to the full prediction). Weekly review weights hit-rate by specificity — a vague PASS is worth less than a specific PASS.

> **S4.4 — Novelty / repetition tracking.** Premarket compares today's prediction array against last 5 days. If ≥3 predictions are structurally similar (same level, same setup, same direction), tag the day as `bias_repetition` and surface in journal as "we've made this prediction before — last X days hit rate on this kind of prediction is Y%."

> **S4.5 — PARTIAL sub-types.** EOD uses sub-codes: `PARTIAL_TIMING` (right call, wrong window), `PARTIAL_DIRECTION` (right level, wrong direction), `PARTIAL_MAGNITUDE` (right direction, didn't go as far as predicted), `PARTIAL_LATE` (right call but too late to act on). Each sub-code has different lessons.

---

## Pillar 5 — Benchmarking (no baseline = no signal)

### What's measured today

`setup-performance.json` tracks per-setup hit rate, expectancy, by_iv_regime, by_tod_bucket. Weekly review shows this week vs cumulative. Live-deployment thresholds (≥45% WR, expectancy > 0, etc.) are checked against cumulative.

### What's NOT measured

We compare ourselves to ourselves. We don't compare to:

1. **Random baseline.** What would a random "buy ATM 0DTE call at a random tick between 09:35-15:50, hold 30 min" strategy have made? If our hit rate is 55% and random is 52%, we have a 3-point edge. If random is 45%, we have a 10-point edge. Without this, we don't know if we're skilled or just present.

2. **VWAP/MA simple strategies.** "Buy SPY 0DTE call when SPY > VWAP for 5 consecutive bars + RSI < 30" is a simple strategy. If a one-rule mechanical strategy beats our discretionary playbook, we have a problem (the playbook is overfit). If we beat it, the playbook earns its complexity.

3. **Buy-and-hold SPY.** If trading 0DTE intraday returns 8% on the year and SPY shares return 11%, we're losing to passive — even with positive expectancy. The whole point of options leverage is to beat SPY by enough to justify the volatility. We don't compute this.

4. **Past-self.** Last 4 weeks vs prior 4 weeks. Is the system getting better, plateauing, or regressing? Cumulative hides this trend.

5. **Process compliance.** % of days where ALL rules were followed (zero rule breaks). This is the leading indicator of long-term success — even more than P&L.

### Gaps

1. **No baseline anchored to the actual data.** The `setup-performance.json#hit_rate = 1.0` after 3 wins is useless without "what's random's hit rate on the same days?"

2. **No drawdown tracking.** Risk-rules.md says "max drawdown ≤ 30% of paper equity." Equity-curve.json captures starting/ending. But max intraday drawdown across the rolling sample? Not computed.

3. **No regime-stratified baseline.** If we win 80% in MID IV and 30% in HIGH IV, and HIGH days are random-baseline 25%, our HIGH performance is still beating random. Without the baseline, we can't tell if we should reduce HIGH-regime trades or just accept lower hit rate as the regime tax.

### Suggestions

> **S5.1 — Random baseline weekly.** Weekly review fetches SPY 5-min bars for each trading day in the week. For each day, simulate 100 random "random tick entry → hold 30 min" trades. Aggregate: random's hit rate on this week's tape, average return per random trade. Add a `random_baseline_this_week` row to `setup-performance.json` so every setup's actual stats display next to the random benchmark.

> **S5.2 — Simple-rules benchmark.** Add a small "benchmark strategies" set: VWAP-cross, RSI-extreme, opening-range-breakout. Each backtested against the same days as the real trading sample. Weekly review shows: "this week — Gamma's setups: hit rate 67%, expectancy +0.31R. VWAP-cross benchmark: 54%, +0.12R. RSI-extreme: 48%, -0.08R. ORB: 51%, +0.04R." If Gamma is below all benchmarks, the playbook needs scrutiny.

> **S5.3 — SPY buy-and-hold equivalent.** Each weekly review: "this week — SPY index +0.8%, paper account +1.4% → +0.6 alpha. YTD: +12.4% account, +9.8% SPY → +2.6 alpha." If alpha is consistently negative, the activity isn't earning its risk.

> **S5.4 — Trailing 4-week vs prior 4-week deltas.** Weekly review § 5.5: "trailing 4 weeks: 60% WR, +0.42R expectancy. Prior 4 weeks: 58% WR, +0.38R. Improving on both axes."

> **S5.5 — Process compliance metric.** Add a top-line metric to weekly review: "process days = N of M (= X% of trading days had zero rule breaks AND no missed-but-should-have-fired skips)." Process compliance is the leading indicator; P&L is the lagging confirmation.

---

## Pillar 6 — Suggestion Pipeline (where evidence becomes action)

### What's deployed

Weekly review § 6 (promote/demote setups) and § 7 (tunings to consider). The `dashboard-dialogue.ticker_speech` carries one short hint into Monday's premarket. Monday's Step 2a surfaces top mistake pattern.

### Gaps

1. **Suggestions buried in markdown.** The weekly review markdown is 1,000+ words. Section 7 has the gold but it competes with 6 other sections. Without an executive summary or "ratify/reject" interface, J might read the whole file or might skip to predictions.

2. **No rejected-suggestions memory.** If J declines S2.1 ("trade grading rubric") in week 4, the system doesn't remember. Week 5's weekly review might re-suggest the same thing. Suggestion fatigue.

3. **No urgency tagging.** A `**REPEATING**` rule break that cost $400 needs J's attention this week. A "consider tightening filter X by 5%" can wait. They look the same in the markdown.

4. **No evidence threshold.** A tuning suggestion based on 3 trades is weak. A tuning suggestion based on 30 trades is strong. The current weekly review doesn't show the evidence weight behind each recommendation.

5. **No "ratification log."** When J approves a suggestion (say, S1.1), there's no `automation/state/ratified-changes.jsonl` capturing: when, which suggestion, J's wording, and which file got edited as a result. A change in the playbook 4 weeks later loses its provenance.

### Suggestions

> **S6.1 — Recommendations executive block.** Weekly review opens with a "Recommendations for J's Monday review" block listing 0-5 specific calls, each with: urgency tag (CRITICAL / HIGH / MEDIUM / LOW), evidence count (n_trades / n_observations), one-sentence ask, accept/reject decision space ("ratify by editing playbook.md line X" or "decline by writing 'declined: <reason>' in `recommendations-log.md`"). Sections 1-7 stay below for the deep evidence.

> **S6.2 — Recommendations log.** New file `analysis/recommendations-log.jsonl`. Each weekly review appends rows: `{week, recommendation_id, type: "promote_setup"|"tune_filter"|"new_rule"|"rule_change", urgency, evidence_count, status: "pending", proposed_at}`. When J ratifies or declines, J appends `{recommendation_id, status: "ratified"|"declined", reason, decided_at}` (or runs a small `/ratify R-0042` command). The next weekly review skips already-ratified-or-declined suggestions if they re-occur, OR flags them as REPEAT-SUGGESTION with J's prior reason.

> **S6.3 — Urgency rubric.** Computed automatically:
> - CRITICAL: a `**REPEATING**` rule break with cost > $200 OR a setup with hit_rate dropping below the deployment threshold mid-trial
> - HIGH: a tuning recommendation with evidence count ≥ 20
> - MEDIUM: tunings with 10-19 evidence
> - LOW: tunings with < 10 evidence (FYI only — should usually wait for more data)

> **S6.4 — Evidence-weight column on every recommendation.** Each weekly review § 6 / § 7 bullet now requires `[n=X, conf=Y]` after the text. Recommendations with n < 5 get a "weak evidence" warning. J can decide to ratify on weak evidence anyway, but it's surfaced.

> **S6.5 — Ratification provenance.** When J ratifies S-id and it results in an edit to playbook.md, the playbook line gets a `<!-- ratified S-0042 from analysis/2026-W12.md week of 2026-03-23 -->` comment. Provenance is one grep away.

---

## Cross-pillar findings

### What's working
- The signal capture layer (P0/P1/P2) is real. Every fact we'd want is being written somewhere durable.
- The schema is good — JSONL ledgers make Sunday rollups straightforward.
- The Monday context block + ticker_speech bridge is the right shape — last week's lesson actually arrives at next week's premarket.
- The bracket-orders + Greeks gate + HTF freshness gate (P0/P1) are concrete behavioral guards, not just observations.

### What's not working yet
- **Subjectivity in grading.** Trade grades, setup_quality, and partly the hypothesis grading still rely on Gamma's free-form judgment at EOD. P0 quantized the heartbeat filters; the EOD grading layer hasn't gotten the same treatment.
- **No counterfactual layer.** Every grade is "what happened." Nothing measures "what would have happened if the rule fired / didn't fire / different exit / different entry timing." Without counterfactuals, we can't tell if our filters are saving us or starving us.
- **No baselines.** Hit rates float in space. Random baseline + simple-rules benchmark would tell us in 4 weeks whether the playbook is earning its complexity.
- **Decisions are invisible.** We grade trades and hypotheses, not the 50+ tick-level decisions that produce them.
- **Suggestions are buried in prose.** The weekly review HAS recommendations but they're not in a ratify/decline workflow.

### What this means for the strategy itself
**Nothing right now.** Per J's constraint, no strategy changes without approval. This audit is a research artifact. If J ratifies any suggestion (S1-S6), it gets implemented as additive measurement infrastructure — nothing in the playbook, risk-rules, or chart-anatomy changes without explicit J approval on the specific edit.

The `recommendations-log.jsonl` (S6.2) is the contract: every suggestion has a record, every J decision has a record, every ratified change has a provenance comment.

---

## Recommendations summary (for J's Monday review)

| ID | Pillar | Urgency | Evidence | One-line ask |
|---|---|---|---|---|
| S1.1 | trade-grading | HIGH | n=3 trades existing | Replace adjective `trade_grade` with 5-point objective rubric |
| S1.2 | trade-grading | MEDIUM | infra | Add counterfactual exit P&L columns to trades.csv |
| S1.3 | trade-grading | MEDIUM | infra | Add archetype similarity score per trade |
| S1.4 | trade-grading | LOW | infra | Add tape-assistance tag |
| S2.1 | mistake-learning | HIGH | infra | Add cost_estimate to rule-breaks.jsonl |
| S2.2 | mistake-learning | HIGH | infra | Add cf-30min P&L to skipped-setups.csv |
| S2.3 | mistake-learning | LOW | infra | Mistake half-life chart in weekly review |
| S2.4 | mistake-learning | MEDIUM | infra | Cluster rule-breaks by (setup, rule_id) |
| S2.5 | mistake-learning | LOW | nudge | Monday narrative-write prompt |
| **S3.1** | **decision-grading** | **CRITICAL** | **none yet** | **Decision-events JSONL — biggest gap, biggest leverage** |
| S3.2 | decision-grading | HIGH | infra | Skip cost retro at EOD |
| S3.3 | decision-grading | MEDIUM | infra | Hold-quality score per trade |
| S3.4 | decision-grading | LOW | infra | Entry timing precision columns |
| S3.5 | decision-grading | LOW | infra | Decision consistency report |
| S4.1 | hypothesis | HIGH | infra | Multiple claims per day (array) |
| S4.2 | hypothesis | MEDIUM | n=5+ predictions | Confidence + calibration tracking |
| S4.3 | hypothesis | MEDIUM | infra | Specificity score per prediction |
| S4.4 | hypothesis | LOW | infra | Novelty / repetition tracking |
| S4.5 | hypothesis | LOW | infra | PARTIAL sub-types |
| **S5.1** | **benchmarking** | **CRITICAL** | **none yet** | **Random baseline — without it, all hit rates are floating** |
| S5.2 | benchmarking | HIGH | infra | Simple-rules benchmark (VWAP, RSI, ORB) |
| S5.3 | benchmarking | MEDIUM | infra | SPY buy-and-hold alpha |
| S5.4 | benchmarking | MEDIUM | infra | Trailing 4w vs prior 4w deltas |
| S5.5 | benchmarking | HIGH | infra | Process compliance metric |
| **S6.1** | **suggestions** | **HIGH** | **infra** | **Recommendations executive block at top of weekly review** |
| S6.2 | suggestions | HIGH | infra | recommendations-log.jsonl with status field |
| S6.3 | suggestions | MEDIUM | infra | Urgency rubric (computed) |
| S6.4 | suggestions | MEDIUM | infra | Evidence-weight on every recommendation |
| S6.5 | suggestions | LOW | infra | Ratification provenance comments |

**Top 3 if you only ratify three:** S3.1 (decision JSONL), S5.1 (random baseline), S6.1 + S6.2 (executive block + log).

Those three change the system from "captures evidence" to "tells you what the evidence means and what it's asking you to do." Everything else amplifies.

---

## What J does next

1. Read this audit when there's 30 min of focused time. Saturday morning works.
2. Per item: ratify (write "✓ S-id approved" + scope) or decline (write "✗ S-id declined — reason"). Append to a new `analysis/ratification-log.md` (or just respond in chat — I'll log it).
3. Ratified items become P3 implementation work. Each is small enough to ship in a 30-90 min session.
4. Declined items move to a deferred list and don't re-surface unless evidence materially changes.

No file in `strategy/`, `playbook.md`, `risk-rules.md`, or `chart-anatomy.md` was edited by this audit. The strategy is yours; this is just the measurement scaffold underneath it asking to be sharper.
