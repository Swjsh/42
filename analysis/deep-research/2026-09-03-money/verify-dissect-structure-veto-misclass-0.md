# VERIFY (skeptic pass) — dissect-structure-veto-misclass

Stamp: 2026-09-03T11:56 ET (market open, read-only pass, no trading-path files touched).
Target report: `analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.md`
Target script: `backtest/tools/dissect_structure_veto_misclass.py`

**Verdict: NOT REFUTED.** Every code-level claim and every headline number was independently
recomputed from raw source/ledger and matched byte-for-byte. One real bug was found in the
report's own methodology (not in its conclusion) — see §4. It does not overturn SUPPORTED; when
corrected, it produces MORE confirmation of the report's "zero effect on named winning days"
claim, not less.

## 1. Code-level claims — all confirmed byte-exact by direct read, not by trusting the report

- `_veto_side` (engine_cli.py:177-189) and `_classify_sameday_5m` (192-224): read directly,
  matches the report's quoted code verbatim, including the `find_swing_points(bars, window=2,
  inclusive_right=True)` call and the `classify_trend`/`label_swings` import (never
  `walk_structure`).
- `grep -n "walk_structure" backtest/lib/engine/engine_cli.py setup/scripts/heartbeat_core.py`
  → **zero matches**, independently reproduced.
- `crypto/lib/market_structure.py` docstrings for `classify_trend` ("fallback before any
  confirmed structure break; `walk_structure` gives the authoritative trend") and `walk_structure`
  ("the authoritative BOS/CHoCH state machine... no look-ahead") — read directly, quotes are
  verbatim, not paraphrased-then-misquoted.
- `crypto/lib/trendlines.py:find_swing_points` — `for i in range(window, n - window)` confirmed:
  with `window=2` the newest 2 bars of whatever's passed can never be evaluated as `i`, so they
  can never become pivots. This is a hard-coded property of the loop bounds, not the report's
  inference.
- `heartbeat_core.py:993-1013` `sameday_5m_bars` construction: `_sameday_mask = (date==trig_date)
  & (ts <= trig_ts)` — read directly, no look-ahead, matches the report's claim.
- Bar-freshness lag claim ("bar `09:30` absent through tick `09:35:03`, present at `09:36:03`;
  bar `11:10` absent through `11:15:xx`, present at `11:16:03`") — **recomputed independently**
  from `core-decisions.jsonl` `bar_freshness.bar_et`: confirmed exactly (09:30 bar first appears
  at the 09:36:03 tick with `age_min=6.06`; 11:10 bar first appears at the 11:16:03 tick with
  `age_min=6.06`). Not paraphrased — pulled the raw field myself.

## 2. Headline SPY-move numbers — recomputed from raw ledger rows, not copied from the report

| Episode | Entry tick | Entry SPY | +30m target | Actual row hit | SPY | Move |
|---|---|---|---|---|---|---|
| 1 | 11:11:04 | 770.73 | 11:41:04 | 11:41:03 | 772.465 | **+1.735** (matches report exactly) |
| 2 | 11:16:03 | 771.50 | 11:46:03 | 11:46:03 | 772.58 | **+1.08** (matches report exactly) |

Both recomputed independently by parsing `automation/state/core-decisions.jsonl` myself (not by
trusting `dissect-structure-veto-misclass.json`). Both match the report's headline numbers
exactly.

**Additional confirming evidence the report did not have yet** (more ticks have landed since the
report was finalized — market is still open): episode 3 (entry 772.02 @ 11:21:03) now has a
completed +30m readout too: SPY 772.935 @ 11:51:07, move **+0.915 — veto wrong a third time**.
Episodes 4 and 5 are still in-flight but trending the same direction (+0.825, +0.005 interim as
of 11:55:05). This is fresh data past the report's cutoff, offered as supplementary confirmation,
not as something the report should have included.

## 3. The two independent-instrument documents — confirmed byte-exact

- `automation/state/gate-registry-status.json` → `gates.structure_veto_enabled`: `overall:
  "YELLOW"`, `pnl_check.combined` = `{n:5, wr_pct:40.0, exp_per_trade:69.7, total_dollar:348.5,
  sign:"POSITIVE", window:"2026-07-29..2026-09-01"}`, verdict reason string **verbatim**:
  `"refused cohort positive ($69.7/tr) but n=5 < floor 10 -- watch, not yet actionable"`,
  `replay_soundness: "sound"`, `replay_engine: "walk_exit_manager"`. All match the report exactly
  — read directly from the JSON, not from the report's quote.
- `analysis/recommendations/structure-veto-lift-prereg-2026-08-04.json`: `n=11`, refused cohort
  `+$38.97/tr` (window `2026-06-26..2026-07-31`), status string **verbatim**: `"PREREG ONLY --
  NOT armed tonight..."`, kill criterion and arming mechanism match.
- `automation/state/params.json:314` → `"structure_veto_enabled": true` — confirmed still live,
  unchanged, over a month after the prereg was written (read-only check, no edit made).
- `analysis/recommendations/structure-veto-ab-2026-06-26.json` (the original ratifying study):
  `full_vetoes/n_vetoes: 107`, `removed_trades: 2`, `removed_winners_full: 0`,
  `removed_losers_full: 2`, `oos_2026.delta_pnl: 0.0` — all confirmed byte-exact.
- Commit provenance: `git show -s --format="%H %ai %s" 26832c07` and `667217a1` both resolve,
  both dated 2026-06-26 (14:15:44 and 15:10:58 -0600), matching the report's citation exactly.

## 4. A real bug found — but it strengthens, not refutes, the conclusion

The report's disclosed limitation — *"the retained live ledger only retains 2026-08-26 through
today... 2026-08-06 and 2026-08-13 cannot be checked from this ledger"* — is **not actually
true**, and the reason is a bug in `dissect_structure_veto_misclass.py`'s `load_rows(date=...)`:

```python
if date is not None and d.get("date") != date:
    continue
```

`core-decisions.jsonl` has **32,739 older-schema rows** (pre-2026-08-26) that carry `ts_et`,
`account`, `action`, `verdict`, `spy`, etc. but **no `date` key at all** — `d.get("date")` returns
`None` for every one of them, so this filter silently drops all pre-08-26 history for *any*
date-scoped query, including the four winner-day checks in §3 of the report (`WINNER_DAYS =
["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]` at line 27, filtered through the same
broken helper). The report's own script logged this as "the ledger doesn't have it" rather than
"my filter returned nothing" — an unverified silent-empty-result treated as a confirmed retention
limit (the failure-honesty class this codebase's C7 lesson index exists for).

I re-ran the check correctly (parsing `ts_et` string-prefix instead of the `date` key) directly
against the raw file:

```
2026-08-06  n_rows=774  accounts={safe,bold}  skip_structure_veto=0
2026-08-13  n_rows=772  accounts={safe,bold}  skip_structure_veto=0
2026-06-26  n_rows=760  accounts={safe,bold}  skip_structure_veto=0   (veto ship date)
2026-07-31  n_rows=772  accounts={safe,bold}  skip_structure_veto=0
```

Full row-level data **does** exist back to at least 2026-06-25 (the file's actual start, not
verified further back). All four named winning days — **2026-08-06, 2026-08-13, 2026-08-27, and
2026-08-28** — show **zero** `SKIP_STRUCTURE_VETO` fires, not just the two the report could check.
This is a strictly stronger version of the report's own "zero effect on winning days" claim — it
does not change the DEFECT verdict, it removes a hedge the report placed on itself unnecessarily.

**Disposition:** flagged as a real defect in the verification script's date-filter (schema-drift
blind spot), not in the report's core reasoning. It inflates the report's stated uncertainty
rather than deflating its confidence — the honest direction of error, just not the correct
diagnosis (the report should have said "my filter returned zero rows, unverified whether that
means no data or a bug" instead of asserting the ledger lacks the history). Recommend: if this
line of investigation continues, fix `load_rows`'s date filter to also accept a
`ts_et.startswith(date)` fallback for pre-08-26 rows.

## 5. Minor internal inconsistency (non-fatal)

The report's own text disagrees with itself on the "last tape row" timestamp: §3 body says
*"last tape row at report-finalization: 11:48:03 ET"* while the Caveats section says *"last tape
row 11:45:04 ET... Only episode 1 has a completed readout"* — but the body two paragraphs above
that already claims episode 2 (target 11:46:03) also completed. These can't both be true at the
same instant. Read as the report being assembled incrementally while the market ticked (this is
expected and disclosed elsewhere — "market was open... throughout this analysis") rather than a
fabricated number: I independently confirmed both episode 1 and episode 2's +30m rows exist and
match (§2 above), so the *numbers* are right even though the *narration* of "how many were
complete when I wrote this sentence" drifted between two sections. Cosmetic, not load-bearing.

## 6. Look-ahead hunt on the proposed fix

- Fix option 1 (`structure_veto_enabled: true → false`, single key) — a config toggle affecting
  only future decisions; no look-ahead surface.
- Fix option 2 (call `walk_structure` instead of `classify_trend`) — `walk_structure`'s own
  docstring states swings become breakable only `window` bars after their pivot, explicitly
  citing "no look-ahead"; read directly, confirmed the confirmation-lag structure matches that
  claim (`by_confirm[s.bar_index + window]` gating, `crypto/lib/market_structure.py:125+`).
- Fix option 3 (document/reduce the `window=2` lag) — not a rule change, a documentation ask.
- None of the three proposed changes were applied (all touch frozen trading-path files); nothing
  in this section introduces future-bar information into a live decision.

## 7. What I did not re-verify

- Did not re-derive `gate_expiry_check.py`'s internal PnL math from raw fills — treated
  `gate-registry-status.json` and the prereg doc as already-computed FACT per this task's own
  disclosure standard (the report does the same, explicitly).
- Did not re-run the report's own reconstruction script (`dissect_structure_veto_misclass.py`'s
  5m-bucketing/swing-classification path) — the report already labels that output APPROXIMATE and
  explicitly says it does not byte-reproduce "downtrend"; I verified the *mechanism* it rests on
  (window=2 exclusion, bar-freshness lag) directly against source instead, which is the stronger
  check.
- Episodes 4 and 5 remain genuinely interim (in-flight) as of this note's timestamp; I did not
  wait for them to complete.

## Bottom line

Refuted: **No.** Confidence: **high**. Every quoted code fragment, every headline dollar/point
number, every cited JSON field, and both git commit hashes were pulled from source and matched
exactly — not one paraphrase-drift or invented figure found. The one bug uncovered (§4) is in the
verification script's own date filter, and correcting it produces a *stronger* version of the
report's already-stated conclusion (0/4 named winning days affected, not 2/4-checked-and-0). No
look-ahead in any proposed change (§6). The DEFECT classification is well-supported: the veto
calls a self-documented non-authoritative fallback, is structurally blind to the newest 10 minutes
of price action, was the *sole* blocker (`bull_blockers: []`, `extra_exec_blocked_by:
"structure_veto"`) on all 17 raw ticks / 5 episodes today, and both instruments that have looked at
its refused cohort (the original 2026-06-26 A/B and the two later `gate_expiry_check.py` runs)
now disagree with each other in opposite directions on whether it helps — with the two most recent
and most complete reads both saying it currently costs money.
