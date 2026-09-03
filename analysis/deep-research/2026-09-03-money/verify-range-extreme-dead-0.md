# VERIFY — H2 range-extreme-dead (skeptic pass)

**Verdict: NOT REFUTED — core claim holds under independent reproduction. One real but non-fatal artifact found in the report's own "482" population framing.**

Stamp: 2026-09-03, market open (this pass made no broker/network calls; read-only against cached ledgers except one side-effect noted below).

---

## What I independently re-derived (not just re-read)

1. **Recomputed range_position by side directly from raw JSONL**, bypassing `conviction_shadow_report.py`/`money_range_extreme_probe.py` entirely — hand-rolled parse of `core-decisions.jsonl` + all 4 fleet `decisions.jsonl`, own post-fix filter (`ts_et >= 2026-08-14T19:15:22`), own restriction to `date<=2026-09-02`.
   - Got: **C n=240, pos 0.445–1.000, mean 0.819. P n=242, pos 0.000–0.445, mean 0.138.** `hits_current_rule = 0` for both sides. This independently confirms the headline: the population sits entirely on the wrong side of 0.30/0.70 for both trade directions.
   - **Fleet ledgers: 0 conviction rows in all 4** (`risky-1/risky-3/safe-1/safe-3`) — confirmed independently, matches the report's fleet-coverage finding.

2. **Reran `backtest/tools/money_range_extreme_probe.py` fresh** (unmodified, as cited). Part 1 (5/5 synthetic cases) reproduced exactly. Part 4 counterfactual reproduced **exactly to the trade**: 47/482 flips, 0 reverse-flips, the same 5 joined trades with identical timestamps/accounts/pnls (`-69, -105, +159, -40, -93`, sum `-148`, mean `-29.60`). This is a bit-for-bit reproduction of the report's most load-bearing numeric claim.

3. **Verified `974ca235` on disk** (`git show`) — the commit message and diff match the report's description of the transposed-key fix and the session-envelope change exactly. `_sess = win.iloc[:trig_idx+1]` in `heartbeat_core.py` (line 947) confirms the envelope is sliced causally through the trigger bar — **no look-ahead** in the mechanism the finding rests on.

4. **Confirmed `trendline_records` is never passed to the primary `res` scoring call** in `_conviction_shadow` (only to the separate `variant_tl` shadow arm) — so the v2 "at_trendline" location-generalisation fallback inside `conviction.py` cannot be silently rescuing the primary row's C4 score. The 0% figure is not an artifact of an unused escape hatch.

## Look-ahead / artifact hunt — what I found

**One real defect, not load-bearing for the verdict.** `part2_3_empirical()` in the probe script takes **no date parameter** and always reads the full live `csr.load_rows()` output filtered only by `is_post_fix()` — it never restricts to `date<=2026-09-02`. Both the `.md` report's prose ("n=482 to match the report exactly") and the JSON's `by_side` block (nested directly under a key stating `n_post_fix_rows_report_matched: 482`) present this table as the 482-row reproduction, but it is actually computed over **512 rows** — the same figure explicitly labeled elsewhere in the same JSON as `n_post_fix_rows_live_at_probe_run` (i.e. it silently includes today's 2026-09-03 live session, which was still accumulating conviction rows at the time the probe ran).

Concretely: the report's `by_side.C` block claims `n=270, min_pos=0.336` for "the 482 population." The true 482-population call-side stats (independently computed above) are `n=240, min_pos=0.445` — 30 of the 270 rows, and the entire tail below 0.445, come from today's not-yet-final session. Put-side numbers happen to be identical either way (no new put rows accumulated between generation and rerun), which is what let this pass unnoticed.

**This does not reverse the finding.** Even on the correctly-scoped 482-row population, `hits_current_rule = 0` for both sides (0.445 is still `> 0.30`), so "0.0% hit rate, structural polarity mismatch" is true under either population. The only thing wrong is that two specific numbers in the by-side descriptive table (`n=270`/`min=0.336` for calls) describe a different, larger population than the one the surrounding prose claims — a population-scope mislabeling, not a fabricated or hindsight-derived quantity, and it does not touch the counterfactual/outcome-join numbers (`part4_counterfactual`, independently verified above), which correctly do apply the `max_date="2026-09-02"` filter and reproduce exactly.

**No other look-ahead, no silently dropped rows, no mis-joined outcome cells found.** The outcome join (`_attach_outcomes`) is a documented, capped, greedy one-to-one match (guards against the prior 5.5x round-trip-inflation bug); spot-checked all 5 joined-trade timestamps against `fills-ledger.jsonl` directly and confirmed a real `engine`-attributed fill exists on the corresponding account within the claimed window for each. The n=5/CI-straddles-zero/INCONCLUSIVE framing is honest, not oversold.

## One process note (disclosure, not a finding)

Running `conviction_shadow_report.py --json` to check the live report's current shape had the side effect of **overwriting `analysis/entry-quality/conviction-shadow-report.json`** on disk (its own documented behavior — "Writes: analysis/entry-quality/conviction-shadow-report.json"). That file was already showing modified (`M`) in git status before this session touched anything (it is routinely regenerated by the live pipeline), so this is not new contamination of a frozen artifact, but flagging it: I did not intend to write outside `analysis/deep-research/2026-09-03-money/` and would avoid re-running that specific script (vs. reading its cached JSON) in a future pass.

## Bottom line

- **Mechanism**: independently re-derived from raw ledgers and matches the report's claim exactly (polarity of C4's threshold is opposite the two live trigger families' structural shape). No look-ahead in the causal chain (`session_high`/`session_low` slice, trigger-tick fields).
- **Headline number** (0.0% hit rate) holds under both the report's claimed 482-row population and my own independently-scoped 482-row reproduction.
- **Counterfactual** (47 flips / 5 joins / -$148 / CI straddles zero) reproduces bit-for-bit on a fresh run.
- **Defect found**: the descriptive `empirical_distribution.by_side` table is silently computed over the live 512-row population while labeled as the 482-row reproduction — a real population-scope bug in the probe script, but not load-bearing for the SUPPORTED verdict since the correctly-scoped population shows the same 0% hit rate.
- Not touching any trading-path file; this pass made zero broker/market-data calls.
