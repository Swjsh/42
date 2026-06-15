# Param Promotion — Stage 2: Quality Review

> **Multi-Agent Gamma 2.0 — Big Win #10 (Stage 2 of 2).** This stage answers:
> **is the gate the right gate?**  Are we measuring the thing that matters?
> Is there a hidden over-fit the spec gates didn't catch?
>
> Stage 1 (`param-promotion-spec-review.md`) is the mechanical pass. This stage is the
> judgment call.

---

## When to invoke

ONLY when Stage 1 wrote `verdict: APPROVE_FOR_QUALITY_REVIEW` to
`{rule_id}-spec-review.json`. If Stage 1 rejected: do not run Stage 2 (no point).

---

## Inputs (provided in context)

- `analysis/recommendations/{rule_id}.json` (the candidate scorecard)
- `analysis/recommendations/{rule_id}-spec-review.json` (Stage 1 output)
- `analysis/recommendations/v15-adversarial.json` (Big Win #2 review verdict)
- `automation/state/params.json` (current production)
- The DIFF: candidate params - production params (what specifically changed)
- Last 30 days `journal/trades.csv`

---

## Quality questions to answer (5 sections)

### 1. Gate validity check

For each gate that PASSED in Stage 1, ask: *is this the right gate to be passing?*
- Was `validate_n_trades >= 20` enough sample to judge? (For 0DTE-style high-variance
  strategies, n=20 still has wide CIs. Push for n=50 if available.)
- Was `dominates` measured against the right baseline? (Should be vs CURRENT production v14,
  not vs initial bag of seeds.)
- Was `sub_window_stable` measured across enough quarters? (5 sub-windows × 1 quarter each is
  ~15 months. Coverage of 2024 data would be stronger but isn't available.)

For each gate, answer YES/NO with 1-sentence reasoning.

### 2. Param-diff sanity

What specifically changed from v14 to candidate? List EVERY param difference. For each:
- Is the change DIRECTION sensible? (e.g., loosening VIX threshold from 17.30 to 17.00 — does
  the live data support this? Did v14 lose specifically when VIX was 17.0-17.3?)
- Is the change MAGNITUDE sensible? (e.g., 1c shift in spread threshold ≠ engine-altering;
  $0.50 shift in stop multiplier ≠ a rounding error)

Output: list of param diffs with sanity verdict.

### 3. Hidden-state dependence

Does the candidate rely on any state field that could be:
- Stale (e.g., `level_states` from a missed bar fetch)
- Corrupt (e.g., `decisions.jsonl` if a tick crash partial-wrote)
- Missing (e.g., dark-pool levels on days when EOD-summary 8c didn't run)

If yes: enumerate. Failure of state = failure of candidate. This is a regression risk Stage 1
can't see.

### 4. Concentration analysis

Is the candidate's edge concentrated in a small number of trades?
- Top 5 winners by P&L: do they account for > 50% of total P&L on validate? (concentration risk)
- Top 5 losers by P&L: did the candidate avoid them by chance or by rule?
- Excluding the top winner: does Sharpe stay positive?

This is the "is one lucky trade carrying the candidate?" check.

### 5. Live-trade consistency

If we have ≥ 5 live trades since the last ratification:
- Replay the candidate against `journal/trades.csv` ENTRY signals
- Would the candidate have entered the same trades? Different ones?
- Of the trades it would have changed: are they (a) winners we'd have skipped, or (b) losers we'd have skipped, or (c) winners we'd have added?

Net live edge: would the candidate have improved live P&L by $X?

---

## Output JSON shape

Write to `analysis/recommendations/{rule_id}-quality-review.json`:

```json
{
  "candidate_rule_id": "v15-...",
  "reviewed_at_et": "ISO",
  "stage": "quality_review",
  "gate_validity": [
    {"gate": "evidence_n_validate", "is_right_gate": true, "reasoning": "..."},
    ...
  ],
  "param_diffs": [
    {"key": "vix_entry_thresholds.bear_min_exclusive_and_rising",
     "v14_value": 17.30, "candidate_value": 17.00,
     "direction_sensible": true, "magnitude_sensible": true,
     "reasoning": "..."}
  ],
  "hidden_state_risks": [
    {"state_field": "level_states", "risk": "stale_after_missed_bar", "severity": "low"}
  ],
  "concentration_analysis": {
    "top_5_winners_pnl_share": 0.52,
    "concentrated": true,
    "sharpe_excl_top_winner": 1.20,
    "concentration_risk_acceptable": true,
    "reasoning": "..."
  },
  "live_trade_consistency": {
    "n_live_trades_compared": 5,
    "n_same_decisions": 4,
    "n_different_decisions": 1,
    "net_live_pnl_delta_dollars": 50.0,
    "live_edge_supported": true
  },
  "verdict": "APPROVE_FOR_RATIFICATION | NEEDS_J_REVIEW | REJECT_QUALITY_CONCERNS",
  "blocking_concerns": [
    {"concern": "...", "severity": "..."}
  ],
  "synthesizer_note": "<2-3 sentence summary for J / weekly-review>"
}
```

---

## Verdict routing

- **APPROVE_FOR_RATIFICATION**: weekly-review Section 7 auto-bumps params.json + rule version
  (with 24-hour silence-is-consent revoke window per CLAUDE.md operating principle 11).
- **NEEDS_J_REVIEW**: weekly-review writes the verdict to dashboard, J reviews Sunday evening,
  no auto-bump.
- **REJECT_QUALITY_CONCERNS**: weekly-review logs the concerns; candidate is dead. J can override
  manually if disagrees, but default is "trust the review."

---

## Single-line emit

```
PROMOTION_QUALITY v15-... verdict=APPROVE_FOR_RATIFICATION concerns={N} concentration_share={X}
```

---

## Cost (operating principle 3)

Quality review uses Sonnet medium-effort, more reasoning than Stage 1. ~$0.05 per promotion.
~$0.20/mo cap (promotions are rare — monthly at most).
