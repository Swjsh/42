<!-- Sonnet overseer 2026-07-02 16:03 ET -->
- **STOP: "write a backtest config JSON"** — free models hallucinate generic EURUSD placeholders with no SPY context. This action has fired at least twice in one morning and produced zero usable output. Retire it permanently.
- **STOP: "check decision-agreement on top contender"** — validator models have no access to `decisions.jsonl` or any live state; they answer "I don't know" every time. Pass raw CSV rows in the prompt or drop the action.
- **STOP: repeating any action whose last output was a hallucination or off-instrument JSON.** Before picking an action, check the last 3 output filenames — if the same verb appears ≥2×, pick a different verb.

---

**Next 4 actions (varied, concrete):**

1. **Rank** — load `analysis/recommendations/contender-rank-2026-06-29.json`, compute `edge_capture` for the top 5 entries, print a table, flag any below the 771 J-edge floor as REJECT. Assign to `analyst` role.

2. **Score the 07:33 ideation** — the `vwap_continuation_rvol_vix_gate` variant from this morning has concrete parameters; run it through `backtest/` via `kitchen_daemon`-style invocation and report expectancy + OOS delta vs baseline `vwap_continuation`. Assign to `coder` lane only if prompt includes the actual parameter dict.

3. **Ideate ONE new family** — level-rejection pullback variant using `NLWB` structure (PDL wick-bounce, N=157, WR=71% in gym). Produce parameter dict only — no JSON boilerplate, no placeholders.

4. **Critique** — send the `gap_and_go` scorecard (`analysis/recommendations/edgehunt-gap_and_go.json`) verbatim to a strategist and ask: "what is the single weakest assumption in this edge claim and how would you stress-test it?"

---

**Rule:** Every output ≤400 words, structured (header + bullets or table), no repeated paragraphs. If a model returns a hallucination ("I don't have information about…"), log it as `SKIP` and do not retry the same action this cycle.
