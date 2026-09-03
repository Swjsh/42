# VERIFY (REPRODUCTION lens) — dissect-sizing-correlation (D6 sizing/correlation)

Stamp: 2026-09-03T11:50 ET (`et_clock.py`, verified fresh this session). Sonnet, read-only,
no broker/market-data/network calls. Independent rebuild — new script written from scratch
(does not import or call the original), against the identical read-only source:
`automation/state/fills-ledger.jsonl`. Original scripts also read for methodology comparison:
[`dissect_sizing-correlation.py`](../../../backtest/tools/dissect_sizing-correlation.py),
[`-part2.py`](../../../backtest/tools/dissect_sizing-correlation-part2.py),
[`-part3.py`](../../../backtest/tools/dissect_sizing-correlation-part3.py). My script:
[`dissect_verify_sizing-correlation_2.py`](../../../backtest/tools/dissect_verify_sizing-correlation_2.py).

**Verdict: CONFIRMED, not refuted.** Every FACT-labeled number in the finding reproduces
either exactly or within rounding from an independently-written script. The APPROXIMATE
flat-3 counterfactual and the design-note H10 correlation figures also reproduce closely/
exactly. One immaterial citation error found (traced below); no numerical or methodological
defect that changes the verdict.

---

## What I rebuilt independently

Same FIFO buy/sell matching logic re-derived from the raw fill schema (not copied), same
filters (`is_option==true`, `attribution=='engine'`), own RNG for the bootstrap, own Pearson
correlation implementation (no numpy dependency — plain Python), separate from the original's
numpy-based one.

Total option/engine fill rows loaded: **979**. Closed round-trip legs (FIFO): **564**.
Unmatched sells: **0** (clean ledger, no orphaned sells in this window).

## 1. Today's trough — CONFIRMED EXACT

| Claim | Reported | My reproduction | Match |
|---|---|---|---|
| Book trough | −$1,045.00 @ 10:37:07 ET | **−$1,045.00 @ 2026-09-03T10:37:07.812088** | exact |
| Book final (closed, this read) | +$836.00 | **+$836.00** | exact |
| safe-2 trough | −$210 @ 10:36:04 | **−$210.00 @ 10:36:04.043750** | exact |
| bold-2 trough | −$155 @ 10:36:06 | **−$155.00 @ 10:36:05.732831** | exact (1s stamp rounding) |
| safe-3 trough | −$335 @ 10:37:06 | **−$335.00 @ 10:37:06.406846** | exact |
| risky-1 trough | −$345 @ 10:37:08 | **−$345.00 @ 10:37:07.812088** | exact (1s stamp rounding) |
| safe-2 final | −$210 | **−$210.00** | exact |
| bold-2 final | +$129 | **+$129.00** | exact |
| safe-3 final | +$605 | **+$605.00** | exact |
| risky-1 final | +$312 | **+$312.00** | exact |

I also independently confirmed the wave attribution: summed every losing leg's `pnl` by hand
from my own leg list. Wave 1 (09:58–10:03 ET stops) = **−$779.00** (bold-2 −85, safe-3 −270,
risky-1 −168−112=−280, safe-2 −144). Wave 2 (10:36–10:37 ET stops) = **−$266.00** (safe-2 −66,
bold-2 −70, safe-3 −65, risky-1 −52−13=−65). **−779 + −266 = −1,045.00**, i.e. literally every
losing dollar today traces to these two waves — matches the report's "8 losing legs, 2 signal
events, 100% of the trough" claim exactly (I count 10 losing *legs* because risky-1's two
FIFO-split sells count as 2 legs per wave, same underlying single sell fill each time — this
is a legs-vs-fills counting nuance, not a dollar discrepancy).

Cross-checked the 5 largest entries in §4 of the report directly against raw buy fills in the
ledger (not through FIFO matching) — every timestamp, qty, and price matches verbatim: safe-3
09:42:06 770C 5×$1.11=$555; safe-3 10:17:07 768C 5×$1.31=$655; risky-1 10:17:09 768C
5×$1.31=$655; risky-1 11:07:10 770C 5×$1.18=$590; safe-3 11:07:15 770C 5×$1.17=$585. Exact.

Also confirmed **no position was left open** as of the ledger's last row (11:34:08 ET) —
net buy-minus-sell qty is zero for every (arm, symbol) pair traded today, so "+$836 closed
legs" is the full realized total at that read, not an understated figure hiding an open
runner.

## 2. Per-arm % figures (equity, dollar-stop, kill-switch) — CONFIRMED

Recomputed all four arms' trough as % of equity, % of the −$400 dollar stop, and % toward
the Rule-5 kill switch, using the equity figures in the task brief. All four match the
report to the first decimal (e.g. safe-2: −210/5653.81 = −3.71%; −210/400 = 52.5%;
−210/−1696.14 = 12.4%). Cross-checked the kill-switch % basis against
`automation/state/fleet/{safe-3,risky-1}/circuit-breaker.json`: `daily_loss_limit_pct` is
**0.3 for safe-3** and **0.5 for risky-1**, confirming the report's (and my) assumption that
risky-1 is governed on the Bold-style 50% kill line, not the Safe-style 30% one — this is not
an assumption, it's read directly from the live circuit-breaker state file. (Note:
circuit-breaker `starting_equity_today` for safe-3/risky-1 is $5,638.63 / $6,148.37 vs the
task brief's $5,639.10 / $6,149.12 — a <$1 difference, immaterial to any %.)

## 3. Correlation matrix, avg rho, effective-N — CONFIRMED (own implementation, own RNG)

Same 19 full trading days (2026-08-06 through 2026-09-02, excl. today's partial session) came
out of my independent per-day per-arm P&L reconstruction — every single day/arm cell matches
the report's Table 1 to the cent (spot-checked all 19 rows against the report's table; no
discrepancy found).

Correlation matrix (own Pearson implementation, no numpy):

| | bold-2 | risky-1 | risky-3 | safe-2 | safe-3 |
|---|---:|---:|---:|---:|---:|
| bold-2 | 1.000 | +0.638 | −0.062 | +0.596 | +0.482 |
| risky-1 | +0.638 | 1.000 | +0.140 | +0.766 | +0.895 |
| risky-3 | −0.062 | +0.140 | 1.000 | +0.478 | +0.227 |
| safe-2 | +0.596 | +0.766 | +0.478 | 1.000 | +0.730 |
| safe-3 | +0.482 | +0.895 | +0.227 | +0.730 | 1.000 |

Identical to 3 decimal places against the report's matrix. Average pairwise rho:
**+0.4890** (reported +0.489 — exact). Effective N via `N/(1+(N-1)*rho)`: **1.6916**
(reported 1.69 — exact).

Bootstrap (own RNG — Python `random`, seed 99001, different from the original's numpy seed
20260903, 3,000 resamples, days with replacement, n=19):

- avg rho: mean **0.4831**, 95% CI **[0.2931, 0.6277]** (reported: mean 0.483, CI
  [0.301, 0.633])
- effN: mean **1.7304**, 95% CI **[1.4242, 2.3018]** (reported: mean 1.73, CI [1.42, 2.27])

CI bounds differ by ~0.005–0.008 from the reported ones, which is exactly the expected
resampling noise between two different RNG streams at n=19, B=3000 — not a disagreement, a
confirmation that the CI is stable under a different seed and a different implementation.

## 4. Flat-3-contracts counterfactual — CONFIRMED (independently reconstructed entries)

Reconstructed entries by grouping FIFO legs on `(arm, symbol, buy_ts_et)` — same key logic as
the original, written independently. Got **222 entries** since 2026-08-06 (reported: 222,
exact). Per-arm actual vs flat-3:

| Arm | n | n>3 | Actual | Flat-3 | Delta | Reported delta |
|---|---:|---:|---:|---:|---:|---:|
| bold-2 | 39 | 36 | +$259.00 | +$67.40 | −$191.60 | −$192 |
| risky-1 | 56 | 49 | +$439.00 | +$286.00 | −$153.00 | −$153 |
| risky-3 | 44 | 41 | −$199.00 | −$111.25 | +$87.75 | +$88 |
| safe-2 | 50 | 0 | +$68.00 | +$68.00 | $0.00 | $0 |
| safe-3 | 33 | 8 | +$473.00 | +$1,050.00 | +$577.00 | +$577 |
| **TOTAL** | **222** | **134** | **+$1,040.00** | **+$1,360.15** | **+$320.15** | **+$320 (+31%)** |

All five arm deltas and the book total match to the dollar (my $320.15 vs reported $320 is
float-rounding on the identical per-contract linear-scaling method, not a different result).
The report's own disclosed caveat — that this ignores the TP1 ladder's nonlinear qty-3-vs-qty-5
split behavior and is therefore directionally biased, not a validated proposal — is accurate
and I have nothing to add to it; I did not attempt a corrected nonlinear version since the
report already declines to treat this as shippable.

## 5. Design-note H10 correlation (0.736 / 0.950) — CONFIRMED EXACT

Recomputed day-summed `actual_walk_pnl` (breakout) vs day-summed `retest_walk_pnl`
(retest-variant, `None`→0 for trades where the retest never triggered) across the 15 days
present in both `retest-entry-variant-walked.json` (zone width 0.30) and
`retest-entry-variant-walked-zw0.50.json` (zone width 0.50). Own Pearson implementation:

- zw 0.30: **r = +0.7364** (reported +0.736 — exact)
- zw 0.50: **r = +0.9504** (reported +0.950 — exact)

Both exceed the 5-arm average pairwise rho (+0.489) and the single highest arm pair
(risky-1/safe-3, +0.895) — confirms the report's point that entry-timing diversification on
the *same* shared signal would not meaningfully decorrelate the book. Also confirmed the
underlying fidelity caveat is real and correctly quoted: `retest-entry-variant.md` lines
158–165 state the walker's magnitude-fidelity vs real fills "PASSES only for safe-2" and the
other arms' dollars are SIGN-ONLY — the sizing-correlation report's citation of this caveat is
accurate, not paraphrased into something stronger than the source supports.

Also independently confirmed the H8 citation (`loss-size-math.md` lines 95–96):
`structure_or_time_loss` 121 legs / 50.6%, `cap_hit` 32 legs / 13.4% — exact match to the
report's "50.6% / 13.4%" figures.

## 6. One immaterial citation issue found

The report says its avg-rho figure "is consistent with MAP.md's own prior figure ('pairwise
r ≈ 0.62–0.72')." I grepped for that figure and it is **not** in MAP.md — it is in
`analysis/compound/MATRIX.md` line 31 ("Effective n (Kish design effect, rho swept
0.62-0.72): 8.75"). Two things worth flagging, neither of which touches the report's own
computed numbers:

- **Wrong source file name** (MATRIX.md, not MAP.md) — cosmetic, easy to fix, does not affect
  any number in the finding.
- **The quantities aren't quite the same thing.** MATRIX.md's "effective n = 8.75" is the
  effective count of independent *arm-day observations* (23 arm-days across 8 sessions,
  correcting for **measured** within-day cross-arm correlation of 0.876–0.985 — a different,
  higher, same-day figure than the 0.62-0.72 *swept* range actually used in its formula) — a
  sample-size-inflation correction for a regression/backtest population. The
  sizing-correlation report's "effective N = 1.69" is the effective count of independent
  *arms* (5 arms, correcting for **day-level P&L correlation across the whole 19-day
  window**) — a portfolio-diversification question. These are legitimately different
  statistics answering different questions; citing one as "consistent with" the other is a
  soft contextual gesture, not a load-bearing equivalence, and it doesn't feed into the
  SUPPORTED verdict's own math. I would not have raised this as an error on the report's own
  terms, since it is presented only as a sanity-check aside — but it deserves a note so a
  reader doesn't go looking for "0.62-0.72" in MAP.md and come up empty.

## Overall assessment

Under a full from-scratch REPRODUCTION lens — new script, no shared code, different RNG,
independent Pearson implementation, independent cross-checks against raw ledger rows and
three separate source reports (H8 `loss-size-math.md`, H10 `retest-entry-variant.md`, and the
live `circuit-breaker.json` state files) — every FACT-labeled number in the finding
reproduces exactly or within float/seed noise. The one APPROXIMATE figure (flat-3
counterfactual) reproduces to the dollar under an independent re-implementation of the same
disclosed method, and the report is honest that this method is not shippable as-is. The one
issue found (a mis-attributed source file for a contextual aside) is cosmetic and does not
touch any number the SUPPORTED verdict depends on.

**Not refuted.**
