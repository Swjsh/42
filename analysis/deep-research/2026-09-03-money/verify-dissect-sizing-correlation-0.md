# VERIFY (skeptic pass 0) — dissect-sizing-correlation

Stamp: 2026-09-03T11:5x ET (`et_clock.py` confirmed `2026-09-03 11:51:12 Thursday EDT`,
market_hours=True). Sonnet, read-only, no broker/market-data/network calls. Independent
re-derivation from `automation/state/fills-ledger.jsonl` and cited source docs, not a re-read of
the target report's own numbers.

**Verdict: NOT REFUTED on its core FACT claims — every trough/wave/sizing/citation number I
independently recomputed reproduces EXACTLY. One real defect found: a mis-cited source
(claims "MAP.md" for a figure that is actually in `analysis/compound/MATRIX.md`) plus a
correlation figure that is stale relative to the project's own recency-over-aggregate doctrine —
material enough to caveat the correlation/effective-N sub-finding, not enough to overturn the
report's headline (today's trough/recovery) or its explicitly-disclosed-as-approximate pieces.**

---

## What I independently reproduced EXACTLY (FACT tier)

Wrote a fresh FIFO matcher (not the report's script, not its scratch output) against the live
`fills-ledger.jsonl` and recomputed from raw rows:

| Claim | Report | My independent recompute | Match |
|---|---|---|---|
| Book trough today | −$1,045.00 @ 10:37:07 ET | −$1,045.00 @ 10:37:07.812088 ET | EXACT |
| Book final (as of 11:34:08 ET read) | +$836.00 | +$836.00 | EXACT |
| Per-arm trough: safe-2/bold-2/safe-3/risky-1 | −210/−155/−335/−345 | −210/−155/−335/−345 | EXACT |
| Wave 1 total (09:41-42 entries, premium_stop) | −$779 | −$779 (−144−270−85−280) | EXACT |
| Wave 2 total (10:16-17 entries, structure_stop) | −$266 | −$266 (−66−70−65−65) | EXACT |
| 5 sizing-table rows (§4): notional, %equity, %Rule6, %$1k | all 5 rows | all 5 rows | EXACT |
| Correlation matrix, avg pairwise rho, n=19 days | +0.489 | +0.489 | EXACT |
| Bootstrap 95% CI on rho (3000 resamples) | [0.301, 0.633] | [0.299, 0.634] (own seed=42 run) | EXACT (same methodology) |
| Effective N (formula) | 1.69, CI [1.42, 2.27] | 1.69, CI [1.41, 2.28] | EXACT |
| Effective N (participation ratio) | 2.19 | 2.186 | EXACT |
| Flat-3 counterfactual, per-arm + book | all 5 arms + total +$320 (+31%) | all 5 arms + total +$320.15 (+30.8%) | EXACT |
| Entry qty distribution (222 entries) | n=222, 134 above floor-3 | n=222, 134 above floor-3 | EXACT |
| Median win/loss/notional, 5 arms | all 5 rows | all 5 rows | EXACT |
| H10 retest-variant day-correlation | r=+0.736 (0.30zw) / +0.950 (0.50zw), n=15 | r=0.736 / 0.950, n=15 | EXACT (recomputed from raw `retest-entry-variant-walked*.json`) |
| PREREG-TIGHT-LADDER dollar-stop backtest ($347 vs $1,948, net +$1,601; loss-count −$306) | cited verbatim | confirmed present verbatim in `PREREG-TIGHT-LADDER-2026-08-28.md:241-243` | EXACT |
| H8 exit-mode stats (structure_or_time_loss 50.6%/n=121, cap_hit 13.4%/n=32, +1.34R/−0.51R) | cited verbatim | confirmed present verbatim in `loss-size-math.md:76,95-96` | EXACT |
| `max_contracts_per_entry=5`, `$1,000` position cap, `-$400`/day, `max_same_day_roundtrips=4` | cited from PREREG/params.json | confirmed present in `params.json` (read-only grep) | EXACT |
| "ELITE tier sizes to 8 contracts at this equity band" | claimed | `params.json:94` doc string: "elite_qty up to 15... at this account's $2K-10K tier (8)... a REAL, currently-binding gap for safe-3" | EXACT |
| Exit-reason attribution: wave 1 = `premium_stop`, wave 2 = `structure_stop @ 768.0` (last_closed_5m_close 767.96) | claimed for all 4 arms | confirmed in `core-decisions.jsonl` (safe/bold) + `fleet/{safe-3,risky-1}/decisions.jsonl` for all 4 arms | EXACT |
| risky-3 "did not trade today" | claimed | 0 decision rows, 0 fills for risky-3 today | EXACT |
| No new fills landed between the report's 11:34 ET read and my 11:51 ET read | implicit (report flags staleness) | confirmed: still 35 today option/engine rows, last ts 11:34:08 | CONFIRMED (report's live-session caveat is honest, not just boilerplate) |
| No trading-path file touched, only allowed new files created | claimed | `git diff --stat` on all 8 protected files: empty; new files are untracked (`??`) and confined to `analysis/deep-research/2026-09-03-money/` + `backtest/tools/dissect_sizing-correlation*.py` | EXACT |

This is an unusually tight report — I could not find a single arithmetic, sourcing-to-ledger, or
methodology error across ~20 independently-recomputed figures spanning FIFO matching, bootstrap
statistics, and cross-document citation checks.

## Extra check I ran that the report didn't: per-day flat-3 delta on the 4 named winning days

The report's `kills_winners` field flags, but does not verify, that "shrinking to 3 would
plausibly have cost money on exactly the days that carry the book" and says this "was not
separately verified per-day in this pass." I ran it:

| Date | Actual $ | Flat-3 $ | Delta |
|---|---:|---:|---:|
| 08-06 | +1,465.00 | +827.85 | **−637.15** |
| 08-13 | +1,748.00 | +1,270.40 | **−477.60** |
| 08-27 | +1,897.00 | +1,536.20 | **−360.80** |
| 08-28 | +1,304.00 | +1,155.40 | **−148.60** |
| **Sum, 4 winning days** | **+6,414.00** | **+4,789.85** | **−1,624.15** |

Confirms the report's own stated concern is correct and larger than implied: on every one of the
four anchor winning days, flat-3 sizing would have cost real money (−$1,624 combined), even
though the FULL-WINDOW aggregate delta is positive (+$320). The report was right to withhold this
from its "not a shippable result" framing and right to flag it as an open risk — I'm noting this
because it strengthens (not weakens) the report's own caution, and any future session tempted to
ship "cap everyone at 3" off this report's aggregate number should be pointed at this table first.

---

## The one real defect: a wrong citation + a recency-blind correlation headline

Report §2 says: *"This is consistent with MAP.md's own prior figure ('pairwise r ≈ 0.62-0.72')."*

- **The citation is wrong.** `MAP.md` contains no such figure (`grep -n "0.62\|0.72\|pairwise" MAP.md`
  returns nothing). The actual source is `analysis/compound/MATRIX.md:31`: *"Effective n (Kish
  design effect, rho swept 0.62-0.72): **8.75**"* — a **sensitivity sweep** used inside a
  different statistic (Kish design effect on arm-*days*, not a same-day cross-arm correlation
  matrix), not itself a measured correlation. Citing it as "MAP.md's own prior figure" that the
  0.489 result is "consistent with" is both a wrong source file and a mischaracterization of what
  that number is.
- **The actual measured correlations in that document are much higher, not similar.** The same
  MATRIX.md paragraph reports *measured* pairwise correlations for the post-fix (≥08-19) regime
  of **[0.876, 0.894, 0.921, 0.932, 0.951, 0.985]** across the same 4-arm roster (safe-2, bold-2,
  safe-3, risky-1) — nowhere near the dissect report's 0.489, and nowhere near the 0.62-0.72
  sweep either.
- **I recomputed this myself** (day-level correlation, 4-arm roster matching MATRIX's own roster,
  restricted to the same ≥08-19 post-fix window, 10 trading days, excluding today):
  avg pairwise rho = **0.732**, with risky-1/safe-3 at **0.989** — materially higher than the
  dissect report's full-19-day, 5-arm-including-retired-risky-3 headline of 0.489. Recomputing
  effective N with N=4, rho=0.732 gives **~1.25** independent bets, not 1.69-2.27.
- **Why this matters:** the project's own standing doctrine (memory:
  `feedback_dynamic_market_recency_over_aggregate_2026_07_31`, "a 390-day aggregate is the wrong
  bar; every armed gate needs a revalidation clock") says recency should dominate a blended
  aggregate. The dissect report's headline correlation blends a lower-correlation earlier regime
  and a since-effectively-idle arm (risky-3, 0 trades since 08-28, near-zero/negative correlation
  to bold-2 dragging the average down) with the current, much tighter regime. The report's own
  wide bootstrap CI [0.30, 0.63] is honest about imprecision, but it doesn't surface that the
  *point estimate itself* is a full-history average sitting below the *recent* regime's own
  measured range — a materially different read on "how diversified is the book right now."

This does **not** touch any of the report's FACT-tier ledger numbers (today's trough/wave/sizing
figures, all exactly reproduced above) and does not change the report's conclusion that no rule
change is proposed (INSTRUMENT_ONLY stands either way). It does mean the "effective independent
bets ~1.7-2.3" framing should be read as a *lower bound on how correlated the book has been*, not
as the *current* state — the current 4-active-arm, post-08-19 regime is trading closer to
**1.2-1.3** effective independent bets, not 1.7-2.3.

---

## Other checks that came back clean (no look-ahead, no proposed rule to audit)

- The finding's `change_class` is `INSTRUMENT_ONLY` and `proposed_change` explicitly ships
  nothing — there is no live rule to audit for look-ahead. The one quantitative sensitivity in the
  report (flat-3 counterfactual) uses only realized fill prices at their own historical
  timestamps, scaled linearly; it does not use any information unavailable at entry-decision time
  and does not touch any live/decision code path. No look-ahead found.
- Wave/exit-reason attribution cross-checked against BOTH the core (safe-2/bold-2) and fleet
  (safe-3/risky-1) decision ledgers independently, not just inferred from fill prices — confirmed
  `premium_stop` for wave 1 and `structure_stop @ 768.0` (5m close 767.96) for wave 2, all 4 arms,
  both waves.
- No trading-path file was modified; new files are confined to the two allowed paths.

---

## Bottom line for the orchestrator

- **Use the report's FACT-tier numbers as-is** — today's trough/recovery, wave attribution,
  position-sizing-vs-caps table, flat-3 counterfactual, and every external citation (PREREG,
  H8, H10) are independently confirmed exact.
- **Downgrade confidence on the correlation/effective-N headline specifically.** Replace or
  caveat "consistent with MAP.md's own prior figure (0.62-0.72)" — that citation is wrong and the
  real comparison (MATRIX.md's measured 0.876-0.985 for the current 4-arm regime) points the
  other way: the book is *more* correlated right now than the full-history 0.489 suggests, and
  effective independent bets in the active regime is closer to ~1.25-1.3, not 1.7-2.3.
- **The flat-3 counterfactual's own caveat is under-stated, not over-stated** — my per-day check
  on the 4 anchor winning days shows an actual −$1,624 combined cost from flat-3 sizing on exactly
  those days, reinforcing (not weakening) the report's "not shippable" verdict on that piece.

No new file conflicts with any other session's in-flight work (checked via `git status`); this
note is a new file only, no edits to the target report.
