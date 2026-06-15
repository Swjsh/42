# Adversarial Bull/Bear Review — v15 Ratification Gate

> **Multi-Agent Gamma 2.0 — Big Win #2.** Source pattern: Jesse Vincent (obra/superpowers),
> "Adversarial review" (blog.fsck.com, 2026-05-01).
>
> Sunday evening, BEFORE any v15.x param promotion, dispatch two opposing sub-agents to review
> the candidate. Whichever finds more serious issues gets +5 points. Critical objections that
> survive both reviews block ratification.
>
> **Why this matters:** v14 was ratified on a 38-day cherry-picked window (2026-03-15 →
> 2026-05-07) where it scored +$4,731. On every broader window, v14 LOSES MONEY. Sole-author
> review of `synthesize_v15.py` would not have caught that bias. Adversarial review is the
> cheapest insurance against repeating it.

---

## When to invoke

- After `setup\run-weekend-research-parallel.ps1` completes PHASE 4 (synthesize_v15)
- BEFORE `weekly-review.md` writes its Section 7 ratification verdict
- Schedule slot: Sunday 19:00 ET (1 hour before weekly-review at 18:00 ET — wait, weekly-review fires AT 18:00, this should be Sunday 19:00 actually. Let me check…)

Actually: weekly-review fires at Sunday 18:00 ET. Adversarial-review must run AFTER
weekly-review reads the v15 scorecard but BEFORE it writes a ratification recommendation. The
cleanest split: weekly-review section 7 invokes this prompt as a sub-step.

So this prompt is INVOKED BY weekly-review, not standalone-scheduled.

---

## Inputs (provided in your context)

- `analysis/recommendations/v15.json` (the candidate scorecard from synthesize_v15)
- `backtest/autoresearch/_state/random_search/random_search_summary.json`
- `backtest/autoresearch/_state/random_search/sub_window_seed{N}.json` for each top candidate
- `automation/state/params.json` (current v14 production)
- The v15 candidate's `params` dict (from random_search_summary.top_candidates[0].params)
- Last 30 days of `journal/trades.csv` (live evidence to compare against backtest)

---

## Step 1 — Dispatch parallel adversarial agents

Use the Agent tool TWICE in a single response (parallel execution per agents.md).

### Agent BULL (defends ratification)

```
Agent(
  description="Bull case: defend v15 ratification",
  subagent_type="general-purpose",
  prompt="<context PLUS the prompt body below>"
)
```

**Bull prompt body:**

> You are the BULL reviewer for v15 candidate ratification. Your job: build the strongest
> possible case for ratifying v15 over v14. Cite specific numbers from the scorecard. For each
> ratification gate (data_hash_match, sub_window_stable, evidence_n>=20, dominates,
> thresholds_4_of_4): explain why this candidate satisfies it.
>
> Output a JSON list of 5-10 numbered ratification arguments, each with:
> - `argument`: 1-2 sentence claim
> - `evidence`: the specific data point from the scorecard or summary
> - `weight`: high | medium | low (your call)
>
> Be aggressive. If the scorecard supports ratification, defend it. You earn 5 points if you
> find more *serious* objections than the BEAR reviewer does — but ONLY if those objections
> are real (don't fabricate; you'll lose all points if you're caught padding).
>
> Output JSON only. No prose preamble.

### Agent BEAR (attacks ratification)

```
Agent(
  description="Bear case: reject v15 ratification",
  subagent_type="general-purpose",
  prompt="<context PLUS the prompt body below>"
)
```

**Bear prompt body:**

> You are the BEAR reviewer for v15 candidate ratification. Your job: find every reason this
> candidate should NOT be promoted to production.
>
> Specifically attack:
> 1. **Cherry-picked windows.** Did the search optimize on a window that happened to favor this
>    config? Compare candidate's val_pnl on `validate_window` vs cross-quarter sub-windows. Is the
>    advantage concentrated in ONE quarter?
> 2. **Sample size.** Are there enough trades on validate to call it statistically meaningful?
>    Threshold: n_val >= 20. Below that = noise.
> 3. **Train-validate consistency.** If train_sharpe is positive but val_sharpe is barely
>    positive (< +0.50), candidate may be regime-specific.
> 4. **Win-rate vs expectancy.** A candidate with WR=8% needs W/L >= 12 to be positive
>    expectancy. Verify the math holds across sub-windows, not just on aggregate.
> 5. **Production drift risk.** Is the candidate a small delta from v14 (low risk) or a
>    significant restructure (high risk)? List every changed param.
> 6. **Live evidence.** Does the last 30 days of journal/trades.csv show the candidate would
>    have improved actual P&L? Replay if possible. (Use the 30-day rolling backtest.)
> 7. **Robustness to hidden state.** Does the candidate rely on any state file that could be
>    corrupted (decisions.jsonl, key-levels.json)? If so, what happens on corruption?
>
> Output a JSON list of 5-15 numbered objections, each with:
> - `objection`: 1-2 sentence claim
> - `evidence`: the specific data point that supports the objection
> - `severity`: critical | high | medium | low
> - `would_block_ratification`: true | false (your call)
>
> Be ruthless. You earn 5 points for finding more *serious* objections than BULL finds — but
> ONLY if your objections are real. Don't pad.

---

## Step 2 — Synthesis (in this orchestrator)

After both agents return, build the verdict:

1. Count `severity == "critical"` from BEAR. Any critical objection → verdict = REJECT.
2. Count `would_block_ratification == true` from BEAR. >= 1 → verdict = NEEDS_REVIEW (J decides).
3. If BEAR returns no blocking objections and BULL has >= 5 high-weight arguments → verdict = APPROVE.
4. Score the round: BULL points + BEAR points. Highest scorer "wins" (informational only).

Write the synthesis to `analysis/recommendations/v15-adversarial.json`:

```json
{
  "candidate_rule_id": "v15-...",
  "reviewed_at_et": "ISO",
  "verdict": "APPROVE | NEEDS_REVIEW | REJECT",
  "bull_arguments": [...],
  "bear_objections": [...],
  "bull_score": 0,
  "bear_score": 0,
  "winner": "BULL | BEAR | TIE",
  "blocking_objections": [...],
  "synthesizer_note": "<1-paragraph summary for J>"
}
```

---

## Step 3 — Output

Single line emit:

```
ADVERSARIAL_REVIEW v15 verdict={APPROVE|NEEDS_REVIEW|REJECT} bull_pts={N} bear_pts={M} winner={BULL|BEAR|TIE} blockers={K}
```

Append to `automation/state/logs/adversarial-review-{date}.log` AND to dashboard-dialogue.json.

---

## Failure handling

- BULL agent fails: write a single auto-bull "satisfies all gates per scorecard" entry, continue.
- BEAR agent fails: ESCALATE — without bear review, default to NEEDS_REVIEW (J must decide manually).
- Both fail: REJECT (no autonomous ratification without review).

---

## Cost

Each adversarial review = 2 sub-agents × ~$0.05 = ~$0.10 per Sunday. ~$0.40/mo.
Minimal. Cheapest insurance.
