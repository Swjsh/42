# PRE-REGISTRATION — SCHEDULED-RELEASE BLACKOUT (B2), 2026-09-03

**Status: FROZEN before any forward shadow data accrues.** Commit timestamp of this file is
the freeze proof. `backtest/tools/release_gap_study.py` (the historical study, already run
against cached data as of this freeze — its output is `analysis/deep-research/2026-09-03-money/
release-gap-study.md`/`.json`, **already-seen data, cited but not re-asked**),
`setup/scripts/release_blackout_shadow.py` (the forward clock) and
`setup/install-release-blackout-shadow.ps1` (its scheduled task) are committed alongside this
file. `ACCRUAL_START_DATE` inside the shadow script is pinned to this build's own date —
no backfill, forward-only by construction, same contract as
`prereg-tp1-r50-forward-shadow-2026-09-03.md`.

Task: B2 SCHEDULED-RELEASE BLACKOUT STUDY + PREREG (kill-type reduction), stamp 2026-09-03T12:40 ET,
depends on B1 (`setup/scripts/macro_calendar.py#scheduled_releases`, confirmed usable this build).

---

## 1. What triggered this

`analysis/deep-research/2026-09-03-money/dissect-wave-autopsy.md` (D1, reused not reproduced)
found today's Wave 1 (09:41 ET entries, four arms, −$779 net) was stopped at the −50%
catastrophe cap by a single-minute quote-tape gap spanning 10:00→10:01 ET on every held
symbol (770C 0.70/0.71 → 0.49/0.50), coincident with the ISM Services PMI release. The same
pattern recurred 2026-08-05 (776C 1-min bars 2.61 → 2.27 → 2.06 at 10:00–10:01, also ISM
Services). The engine has **no event blackout of any kind** — the retired `macro-veto-v2`
params keys were `CONFIRMED_DEAD` 2026-08-29 (never consumed), and `macro_calendar.py`'s prior
calendar never listed ISM at all (B1's fix). This prereg tests whether a calendar-known (not
release-VALUE-known) blackout would help, on cached history, before any live change ships.

## 2. What is being judged

Three candidate rules, all using **ENTRY-TICK information only** — the release *calendar* is
known premarket (`scheduled_releases(date)` needs only the date), the release *value* is never
known until the print — no look-ahead, guarded by
`test_release_blackout_shadow_2026_09_03.py::test_rule_reads_calendar_never_realized_move`.
All three are scoped to **ISM-only** (`severity="high"`, `type` starting `ism_`) — this task's
own wording calls it a "tier-1 10:00 release"; Consumer Confidence / UMich (`severity="med"`,
`RULE_BASED_UNVERIFIED`) are a **measurement cohort only** (§1/§2 of the historical study), not
in the frozen rules' scope. This matters concretely: 2026-08-28, one of the four named winning
days, carries a `umich_sentiment_final` release — the frozen ISM-only rules never touch it.

- **R1** (ship candidate): no new entries in `[T-15, T+5) = [09:45, 10:05)` ET on an ISM day.
- **R2** (study/comparison arm ONLY, not a ship candidate per this task's own phrasing "ship
  R1 (or R3)"): R1 + no new entries in `[09:35, T+5) = [09:35, 10:05)` ET on an ISM day — this
  kills the entire pre-release morning down to the engine's own existing 09:35 entry gate.
  Reported for transparency; never itself eligible to ship under this prereg.
- **R3** (ship candidate, kill-type): R1 + flatten any position still open at `T-2 = 09:58` ET
  on an ISM day. Kill-type by construction — it can only close a position earlier or enter one
  fewer time, never enter more or hold longer, which is why it (unlike R2) qualifies for the
  2026-09-29 kill-type-reduction bundle per this task's own framing.

## 3. Historical read as of this freeze (already-seen data — cited, not re-tested forward)

Full detail: `analysis/deep-research/2026-09-03-money/release-gap-study.md`/`.json`
(`backtest/tools/release_gap_study.py`, run against 44 cached trading days 2026-06-26..
2026-09-02 plus today's real fills). Five ISM days have an archived SPY 1-min cache in that
window (2026-07-01, 07-06, 08-03, 08-05, 09-01); 2026-09-03 (today, also ISM) is in scope for
the fills-ledger-driven sections only — its SPY/option 1-min cache has not archived yet
(market open at build time).

| Rule | n trades/positions | net (or delta) | ex-best-day (drop-best-day) | evidence base | 4 named big days touched |
|---|---:|---:|---:|---|---|
| R1 | 3 | +$305.00 | **$0.00** | 1 day only (2026-08-05) — degenerate | none |
| R2 (comparison only) | 11 | +$618.00 | **−$161.00** | 3 days | none |
| R3 | 3 | −$42.00 | **$0.00** | 1 day only (2026-08-03) — degenerate | none |

**Read, stated plainly:**
- **R1 does not even touch today's actual triggering loss** — Wave 1 entered at 09:41:04–09:42:08
  ET, four minutes *before* R1's window opens at 09:45. Its entire historical evidence is a
  single day (2026-08-05, n=3 correlated legs of one signal). "$0.00 after drop-best-day" is
  technically `>= 0` but is not real evidence — dropping the only day that ever fired leaves
  nothing, not a margin.
- **R2 (comparison only) fails the bar outright**: dropping the single best day (which is
  *today*, 2026-09-03, contributing +$779 of its +$618 total) flips the ex-best-day total to
  **−$161**. Every dollar of R2's positive historical case comes from one day already known at
  freeze time — the opposite of the forward-shadow's whole purpose.
- **R3 is directionally negative** and, like R1, rests on a single day (2026-08-03, n=3): of
  71 ISM-day positions in scope, 68 had not even entered yet by 09:58 ET (most engine entries
  on these days come later in the morning — e.g. today's paying Wave 3 was 11:06 ET) and 5 more
  lack cached option-bar coverage to price the 09:58 counterfactual mark, leaving only 3
  costable. Flattening at 09:58 cost a small amount on the one day it could be measured (SPY
  kept running past 09:58 rather than gapping).
- **None of the four named big winning days is touched by any frozen rule** (08-06, 08-13,
  08-27 have no 10am release at all; 08-28's release is secondary/UMich, out of the ISM-only
  scope) — the "don't kill a winning day" guard is clean by construction here, not by luck of
  the sample.
- **SPY/option gap distribution (§2 of the study)**: ISM-day mean worst-1-min-adverse option
  move is −12.5% (CI [−18.8%, −6.5%], n=5 days) vs −8.6% on non-release days (CI [−11.2%,
  −6.1%], n=33 days) — modestly worse, CIs overlap. Non-release days already produce a
  >=15%-adverse 1-min move on 6 of 33 days (18%) — big single-minute 0DTE swings are not
  exclusive to release mornings; the release-day tail is somewhat fatter, not categorically
  different. This is consistent with `SYNTHESIS.md`'s book-wide finding: no entry-tick feature
  tested so far cleanly separates a trend day from a chop/gap day.

**Verdict on historical data alone: NONE of R1/R2/R3 clears "net >= 0 after drop-best-day" with
real evidence.** R1 and R3 pass the letter of the rule only via n=1-day degenerate samples; R2
fails outright. Per §4, nothing ships on this reading — the forward shadow is required before
either R1 or R3 becomes ship-eligible, and it may never clear.

## 4. Forward bar + decision rule (frozen — NOT softened after data starts arriving)

`setup/scripts/release_blackout_shadow.py` runs nightly. For each session that was an ISM day,
it reads the 1-minute moves inside the blackout window from the best available cached source
(1-min option-bar archive once it lands, quote-tape while the day is still recent — logged
which source, never guessed) and logs what R1/R2/R3 would have done to that day's REAL fills
(`analysis/recommendations/release-blackout-shadow-ledger.jsonl` +
`release-blackout-shadow-summary.json`).

**Bar (both required before either R1 or R3 may be read as a verdict):**
- **>= 3 forward ISM release days accrued**, AND
- **>= 2 of those >= 3 days show a >= 15% adverse 1-minute option move inside the blackout
  window** (the same `worst_adverse_1000_1001_pct <= -15.0` metric `release_gap_study.py`
  already computes historically — 2 of 5 historical ISM days already clear this bar, so the
  forward bar is calibrated to the same base rate, not an arbitrary number).

**Decision rule, per candidate (R1 and R3 only — R2 is never ship-eligible under this prereg,
per §2):** once the bar is met, a rule ships as a **candidate for a real ratification pass**
only if ALL THREE hold on the accrued forward ledger:

1. **Historical-style net (recomputed on forward-only data) is `>= 0` after drop-best-day**
   (same methodology as §3's table: `total - best_single_day_contribution`).
2. **None of the four named big winning days (2026-08-06, 08-13, 08-27, 08-28) loses more
   than 10% of that day's actual P&L** — trivially satisfied while those four stay outside the
   ISM calendar (confirmed §3), re-checked every run in case a future month's ISM date ever
   coincides with a day this list is extended to include.
3. **The forward-bar condition itself** (>= 3 release days, >= 2 with a >= 15% adverse move) —
   restated here because reaching the bar is the *permission* to read the verdict, not the
   verdict itself; a bar that is met by luck on exactly 3 days with thin n per day is weaker
   evidence than one met at 3 days after a longer accrual — the summary's `days_accrued` and
   `n_ism_release_days` are both reported so a reader can judge margin, not just pass/fail.

**Falsifier (stated once, applies to both candidates):** if, at any point after the bar is
first met, the ex-best-day forward net for a candidate is negative, OR fewer than 2 of the
first 5 forward ISM release days show a >= 15% adverse 1-minute move inside the blackout
window, that candidate is **REFUTED** — retired from ship-eligibility without shipping, and
this prereg's decision rule is not re-opened to rescue it (no re-spec of the 15%/count bar
after the fact, exactly the DO-NOT `tp1_r50_forward_shadow`'s own prereg states for gate G4).

## 5. What this instrument is not

Descriptive + shadow-only, same two-step contract as `tp1_r50_forward_shadow.py`'s own
docstring: it writes a ledger + a summary, flips no engine parameter (`macro_calendar.py`'s
`build_news_json`/`compute_no_trade_windows` output is unread by the entry gate today — this
study does not change that), proposes no change on its own, and places no order. A positive
verdict here is the PERMISSION for a separate, later ratification decision (2026-09-29
kill-type bundle, R3 only, since R1 is not kill-type and R2 is out of scope) to cite this
ledger as its forward evidence base — never sufficient by itself.

## 6. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "SCHEDULED-RELEASE-BLACKOUT",
    "task_slug": "B2",
    "depends_on": "B1 (setup/scripts/macro_calendar.py#scheduled_releases)",
    "frozen_date": "2026-09-03",
    "accrual_start_date": "2026-09-03",
    "backfill": "none -- forward-only by construction",
    "kill_type_classification": {
      "R1": "NOT kill-type (a new entry gate, not a close-earlier rule) -- excluded from the 2026-09-29 bundle even if it ships",
      "R2": "study/comparison arm only -- never ship-eligible under this prereg",
      "R3": "KILL_TYPE_REDUCTION -- bundle-eligible 2026-09-29 IF it clears this prereg's bar"
    },
    "scope": {"tier": "ISM only (severity=high, type startswith 'ism_')",
               "secondary_cohort_measured_not_ruled": ["consumer_confidence", "umich_sentiment_prelim", "umich_sentiment_final"]},
    "windows": {"R1": "[09:45,10:05) ET on ISM day",
                "R2_comparison_only": "[09:35,10:05) ET on ISM day",
                "R3": "R1 + flatten open position at 09:58 ET on ISM day"},
    "historical_read_at_freeze": {
      "R1": {"n": 3, "net": 305.00, "ex_best_day": 0.00, "days": 1},
      "R2": {"n": 11, "net": 618.00, "ex_best_day": -161.00, "days": 3},
      "R3": {"n": 3, "net": -42.00, "ex_best_day": 0.00, "days": 1}
    },
    "bar": {"min_forward_ism_release_days": 3, "min_days_with_ge15pct_adverse_move": 2, "of_days": 3},
    "decision_rule": {
      "ex_best_day_net_gte_zero": true,
      "no_named_big_day_loses_more_than_10pct_pnl": true,
      "bar_condition_itself": true,
      "all_required": true,
      "softenable": false,
      "ship_eligible_candidates": ["R1", "R3"],
      "never_ship_eligible": ["R2"]
    },
    "falsifier": "ex-best-day forward net negative for a candidate at any point after the bar is first met, OR fewer than 2 of the first 5 forward ISM days show a >=15% adverse 1-min move -- REFUTED, retired, bar not re-opened",
    "artifacts": {
      "historical_study_md": "analysis/deep-research/2026-09-03-money/release-gap-study.md",
      "historical_study_json": "analysis/deep-research/2026-09-03-money/release-gap-study.json",
      "historical_study_script": "backtest/tools/release_gap_study.py",
      "shadow_ledger": "analysis/recommendations/release-blackout-shadow-ledger.jsonl",
      "shadow_summary": "analysis/recommendations/release-blackout-shadow-summary.json",
      "shadow_builder": "setup/scripts/release_blackout_shadow.py",
      "shadow_tests": "backtest/tests/test_release_blackout_shadow_2026_09_03.py",
      "scheduled_task": "Gamma_ReleaseBlackoutShadow",
      "install_script": "setup/install-release-blackout-shadow.ps1"
    },
    "do_not": [
      "soften the 15%/count bar or the ex-best-day>=0 rule after data starts arriving",
      "let R2 ship under this prereg -- it is a comparison arm only",
      "read release VALUE (vs calendar DATE) at decision time -- no look-ahead, guarded by test"
    ]
  }
}
```

## 7. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_ReleaseBlackoutShadow
-Confirm:$false` + delete `setup/scripts/release_blackout_shadow.py` +
`setup/install-release-blackout-shadow.ps1` + `backtest/tools/release_gap_study.py` + this
file + the `analysis/deep-research/2026-09-03-money/release-gap-study.*` outputs +
`analysis/recommendations/release-blackout-shadow-*` outputs. Nothing on the trading path
depends on this instrument today (`macro_calendar.py`'s no-trade-window computation is
already unread by the live entry gate) — it is an analysis-only leaf, same class as
`Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.
