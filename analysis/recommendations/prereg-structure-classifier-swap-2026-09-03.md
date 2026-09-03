# PRE-REGISTRATION — STRUCTURE CLASSIFIER SWAP, 2026-09-03

**Status: FROZEN before any forward data accrues.** Commit timestamp of this file is the
freeze proof. `setup/scripts/structure_classifier_shadow.py` (the ledger/summary builder)
is committed alongside this file, `FREEZE_DATE = "2026-09-03"` inside it — the DECISION
clock (the forward bar in §4 and the decision rule in §5) only counts ticks dated on/after
this date. This prereg does **not** gate the historical/backfilled portion of the ledger
(2026-07-06 forward, used descriptively — see §7) — only the forward window may ever be
read as a ship/no-ship verdict.

Queue item: `STRUCTURE-VETO-CLASSIFIER-FIX` (this file is the EVIDENCE half; the classifier
swap itself — editing `backtest/lib/engine/engine_cli.py:203-224` to call `walk_structure`
instead of `classify_trend` — is a separate, later, **2026-10-30** item, gated on this
ledger reaching its bar and clearing this decision rule. `engine_cli.py` is a frozen
trading-path file for the duration of this evidence-gathering task; nothing here edits it.)

---

## 1. What is being judged

Whether `_classify_sameday_5m` (`backtest/lib/engine/engine_cli.py:192-224`) should call
`crypto.lib.market_structure.walk_structure` (the module's own self-documented
**authoritative** BOS/CHoCH state machine — zero live callers today, confirmed by grep)
instead of `classify_trend` (the module's own self-documented **tentative fallback**,
the only one the live structure veto has ever used). Both are fed the SAME
`find_swing_points(window=2, inclusive_right=True)` swings — this prereg is about which
function reads those swings, not about the swing-detection window itself.

## 2. Why a forward shadow, not a same-day verdict (the defect is real, the fix is not free)

- **The defect is code-confirmed** (`analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.md`,
  §1–§4): `classify_trend`'s "last two highs, last two lows" comparison can stay frozen on
  stale pivots through an active rally because `find_swing_points(window=2)` structurally
  cannot confirm the newest 10 minutes of bars fed to it, on any day, unconditionally.
- **The fix is NOT free.** `analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md`
  (§4, §4a) — a same-day companion investigation — found the flip is genuinely contested:
  a full production-replay battery (`gate-revalidation-structure_veto-2026-08-23-extended.json`,
  n=15, `NOT-UNBLOCK-ELIGIBLE`, `"DO NOT FLIP"`) disagrees with a thinner nightly instrument
  (`gate-registry-status.json`, n=5, YELLOW-but-positive) and with today's own fresh 5-episode
  cluster (5/5 favorable at +30m). **Swapping classifiers is not the same change as disabling
  the gate** (that package's proposal) — walk_structure would still veto SOME entries, just a
  different set — so neither of those prior verdicts settles THIS question either way. This
  shadow measures the swap specifically, forward, on data nobody has cherry-picked.
- **This build's own first pass already found a reason for caution the D7/B3 reports never
  checked**: on the two of the four named winning days that have any ENTER_BULL/ENTER_BEAR
  ticks early enough to test (2026-08-06, 2026-08-13), `walk_structure` **would have vetoed 5
  entries on each day** (see the ledger's `winner_day_check`, computed this build). The other
  two winning days (08-27, 08-28) show zero. This is exactly the floor this prereg's ship
  condition is built to catch — a classifier can be "more correct" in aggregate and still
  cost the specific sessions the whole book's live-money case rests on.

## 3. Population and measurement (frozen)

- **Scope: `account="safe"` only** — the only account where `structure_veto_enabled` is
  `true` (confirmed empirically this build: zero `SKIP_STRUCTURE_VETO` rows exist for
  `account="bold"` anywhere in the retained `core-decisions.jsonl`; `bold`'s own
  `aggressive/params.json` carries an explicit `false` since 2026-08-12).
- **Per-tick, for every `SKIP_STRUCTURE_VETO` tick AND every `ENTER_BULL`/`ENTER_BEAR` tick**
  (so the comparison is not conditioned on vetoes alone) since the veto's own first live fire
  (found dynamically from the ledger each run, not hardcoded — `2026-07-06T13:11:27` at this
  build's time):
  - Same-day 5m bars rebuilt strictly up to and including the tick's own logged
    `trigger_bar_et` (no look-ahead; test-proven). Real continuous-tick bars from the frozen
    `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` cache where the date is covered
    (verified this build to byte-reproduce a real logged "downtrend" verdict exactly);
    APPROXIMATE reconstruction from the per-minute `spy` tape in `core-decisions.jsonl`
    otherwise (every date from 2026-09-03 forward, since the cache is a frozen artifact this
    module never refreshes and makes no network call to update).
  - `label_live` — the REAL `_classify_sameday_5m`, imported directly from
    `backtest.lib.engine.engine_cli`, never reimplemented.
  - `label_walk` — `walk_structure(bars, swings, window=2)` on the SAME swings.
  - `agree = (label_live == label_walk)`.
  - Forward SPY move at +30/+60 min from the SAME bar source, in the tick's own side's
    favorable direction (`C`=bull=favorable-up, `P`=bear=favorable-down).
- **"Veto-correct"** (either classifier) = the forward move was **NOT** favorable to the
  blocked/entered side — i.e. the classifier's veto (real or hypothetical) would have
  correctly kept the book out of a loser.
- **No look-ahead, no backfill for the DECISION**: the ledger itself backfills descriptively
  from 2026-07-06 (§7), but `FREEZE_DATE = "2026-09-03"` bounds everything the decision rule
  in §5 is allowed to read.

## 4. Forward bar (frozen — NOT softened at read time)

Both conditions required, counted only on ticks dated `>= 2026-09-03`:

- **>= 20 forward trading sessions accrued**, AND
- **>= 30 forward ticks where `label_live != label_walk`** (a disagreement floor — the
  question is meaningless below a minimum number of ticks where the two classifiers would
  actually have produced a different outcome for the book).

Below the bar the ledger's `forward_decision_clock.status` is `ACCRUING` and produces NO
ship/kill signal — `forward_sessions_to_bar` / `forward_disagreement_ticks_to_bar` name the
remaining distance every run.

## 5. Decision rule (frozen — the bar cannot be softened after data starts arriving)

Once the bar in §4 is met, the classifier swap becomes eligible for the **2026-10-30**
ratification decision ONLY if BOTH hold on the accrued forward ledger:

1. **`walk_veto_correct_rate_30m.ci_lower_2.5 > live_veto_correct_rate_30m.ci_lower_2.5`**
   — walk_structure's own veto-correct rate (computed on the `ENTER_*` ticks it alone would
   have blocked) must clear a bootstrap-CI-lower bound that exceeds the live classifier's own
   veto-correct-rate CI-lower bound (computed on the ticks it actually vetoed), both over the
   SAME forward window. Comparing lower bounds directly (not a paired difference) is
   deliberately conservative — it is not enough for the point estimates to differ, the worse
   classifier's optimistic tail must not even reach the better classifier's pessimistic tail.
2. **Zero of the four named winning days' entries are vetoed by walk_structure**
   (`any_winner_day_entry_would_be_vetoed_by_walk` in the summary — checked against the FULL
   backfilled history in §7, not just the forward window, since all four days are historical).
   This condition is already known NOT to be forward-checkable in the usual sense (the four
   days already happened) — it is a permanent floor-check re-run every night against the same
   fixed four dates, not something that can newly pass or fail as forward data accrues, and it
   **already reads FALSE at freeze time** (2 of 4 days would have had entries vetoed — see §2).
   Per this rule, THE SWAP DOES NOT SHIP ON 2026-10-30 unless this specific finding reverses,
   which would require either new evidence this build could not see, or a scope narrower than
   "swap the classifier everywhere" (e.g. gating the swap to specific hours/regimes) — a
   redesign, not a parameter the forward clock alone can pass.

**Falsifier (stated in advance):** if, at the 2026-10-30 review, EITHER (a) the bar in §4 is
unmet, OR (b) `walk_veto_correct_rate_30m`'s CI-lower does not exceed the live rate's CI-lower,
OR (c) `any_winner_day_entry_would_be_vetoed_by_walk` is still `true` — the swap DOES NOT SHIP.
No single piece of favorable evidence (a good day, a good week, today's own 5/5 cluster)
overrides an unmet bar or a failed condition. This rule is not re-opened after the fact.

## 6. What this instrument is not

Descriptive and shadow-only. It never edits `engine_cli.py`, `params.json`, or any
trading-path file (read-only imports only), flips nothing, places no order, and is never
itself sufficient to ship the swap — a positive verdict here is the PERMISSION for the
separate 2026-10-30 decision to cite this ledger as its forward evidence base, the same
two-step contract every sibling shadow clock in this repo already uses.

## 7. What the ledger ALSO reports (descriptive, not part of the frozen decision rule)

Because `core-decisions.jsonl` already retains full history back to the veto's actual first
live fire (2026-07-06 — an earlier report's claim that retention only reached back to
2026-08-26 was itself a bug in a scratch script's date filter, corrected in
`structure-veto-lift-package-2026-09-05/README.md` §3.4), the ledger backfills descriptively
from that date forward: overall agreement rate, the live-veto-episode favorable/correct
rates split by whether walk_structure agreed (with a bootstrap CI on the rate DIFFERENCE),
the walk-only-veto cohort's own rates, and the three named tick quotes for today's episode
(11:16/11:21/11:27 ET). This historical section is context for the 2026-10-30 review, not
itself a ship signal — only §4/§5's forward-window numbers are.

## 8. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "STRUCTURE-VETO-CLASSIFIER-FIX",
    "half": "evidence",
    "code_fix_scheduled": "2026-10-30",
    "frozen_date": "2026-09-03",
    "freeze_date_for_forward_clock": "2026-09-03",
    "backfill": "descriptive only, from 2026-07-06 (veto's own first live fire) -- NOT part of the frozen decision rule",
    "population": {
      "account_scope": "safe",
      "verdicts_scored": ["SKIP_STRUCTURE_VETO", "ENTER_BULL", "ENTER_BEAR"]
    },
    "bar": {
      "min_forward_trading_sessions": 20,
      "min_forward_disagreement_ticks": 30
    },
    "decision_rule": {
      "walk_ci_lower_gt_live_ci_lower": true,
      "zero_winning_day_entries_vetoed_by_walk": true,
      "all_required": true,
      "softenable": false,
      "known_at_freeze_time": {
        "zero_winning_day_entries_vetoed_by_walk": false,
        "note": "2026-08-06 and 2026-08-13 each show 5 entries walk_structure would have vetoed; 08-27/08-28 show 0. This condition already reads FALSE and would need to reverse, or the scope would need to narrow, for the 10-30 swap to ship as currently framed."
      }
    },
    "artifacts": {
      "ledger": "analysis/recommendations/structure-classifier-shadow-ledger.jsonl",
      "summary": "analysis/recommendations/structure-classifier-shadow-summary.json",
      "builder": "setup/scripts/structure_classifier_shadow.py",
      "scheduled_task": "Gamma_StructureClassifierShadow",
      "install_script": "setup/install-structure-classifier-shadow.ps1",
      "guard_test": "backtest/tests/test_structure_classifier_shadow_2026_09_03.py",
      "source_dissection": "analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.md",
      "related_contested_package": "analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md"
    },
    "do_not": [
      "edit backtest/lib/engine/engine_cli.py before 2026-10-30",
      "soften the decision rule in section 5 after data starts arriving",
      "treat a good week or a favorable single-day cluster as sufficient without the bar in section 4"
    ]
  }
}
```

## 9. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_StructureClassifierShadow
-Confirm:$false` + delete `setup/scripts/structure_classifier_shadow.py` +
`setup/install-structure-classifier-shadow.ps1` + this file +
`analysis/recommendations/structure-classifier-shadow-ledger.jsonl` +
`analysis/recommendations/structure-classifier-shadow-summary.json`. Nothing on the trading
path depends on this instrument — it is an analysis-only leaf, the same class as
`Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.
