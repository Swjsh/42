# Tickers-lane sizing review — is the 1% daily kill switch inconsistent with 3-lot sizing?

**Filed:** 2026-09-05 01:xx ET, conductor AFTERHOURS (weekend-plan item 3: "pre-register a
per-trade $ risk cap consistent with the 1% kill (or raise the kill to Rule-6 shape) in
writing; keep max_contracts 3"). This IS that write-up.

**Trigger:** 2026-09-05 00:02 ET Fable EOD audit flagged AMBER: "QQQ 3-lot @1.87 = $561 at
risk = 11% of equity on a 1%-kill arm."

## The numbers (verified against real broker fills, not estimated)

| Arm | Contract | Qty×Premium | Entry $ | Realized P&L | % of $5,000 SOD equity |
|---|---|---|---|---|---|
| tickers-1 | AMZN 260904C260 | 3×0.79 | $237 | -$156 | 3.12% |
| tickers-2 | AVGO 260904P355 | 3×0.81 | $243 | -$93 | 1.86% |
| tickers-3 | QQQ 260904C720 | 3×1.87 | $561 | -$396 | 7.92% (inflated — see below) |

Source: `automation/state/tickers/{arm}/ledger.jsonl` ENTRY_FILLED/EXIT_FILLED rows, cross-checked
against `day-2026-09-04-eod.json`'s broker-truth equity reads. All three arms correctly latched
their in-memory `kill_tripped` after this single fill (25 `BLOCKED "daily kill switch already
tripped"` rows across the 3 ledgers) — the `false` value in the persisted `day-*.json` was a
separate, already-fixed reporting bug (commit in `prereg-tickers-theta-budget-cadence-2026-09-05.json`),
not a control failure.

**tickers-3's 7.92% is a confound, not steady-state:** entry fired at 09:51:35 ET, exactly when
the box lost power (09:51:05 ET, System log Kernel-Power 41); the position could not be checked
again until 10:47:32 ET when the box came back — 56 minutes with zero monitoring on a 0DTE
option. The intended `-50%` catastrophe stop / `30%` theta-budget cap never got a chance to fire
on schedule; the exit only executed once the box resumed, at whatever price the market had moved
to by then (71.7% bleed on bid, 70.6% on fill). This is the **same root-cause outage** already
tracked for the SPY engine's `rth_tick_gaps` RED (`engine-health.json`, 2026-09-04 09:51→10:46
ET core-decisions gap) — one box crash produced correlated, non-independent tail risk across
**two separate lanes simultaneously** (SPY safe-2/bold-2 AND tickers-3). That is a fact worth
carrying forward: the off-box dead-man's-switch item (queue.md `OFF-BOX-DEADMAN-SWITCH`,
status `awaiting-j`) protects *every* lane that trades during RTH, not just SPY.

## Is the 1% kill switch actually broken?

**No — it is mislabeled, not malfunctioning.** Given Rule-6's floor (`min_contracts: 3`, cannot
go lower without abandoning the 2-TP+1-runner structure) and the current universe's real 0DTE
premiums ($0.79–$5.00 range, bounded above by `per_trade_risk_cap_pct=0.30` → $1,500 max
affordable 3-lot), **any single trade with a real loss already exceeds 1% of a $5,000 account
on its own** — cheapest observed loss (AVGO, 1.86%) is already ~2x the threshold. So in
practice `daily_loss_kill_switch_pct: 0.01` does not function as a multi-trade daily *budget*;
it functions as **"the first trade with a real loss ends the arm's day"** — which day one's
broker-truth fills confirm happened correctly, three times, blocking further entries as designed.

That is a *conservative*, not a *dangerous*, control at this equity tier. The actual worst-case
tail is bounded by the exit ladder, not the kill switch:

- **Theoretical ceiling** (a max-affordable $5.00-premium name, catastrophe stop at -50%,
  no outage): 3 × $5.00 × 100 × 0.50 = **$750 = 15.0% of $5,000 equity**, in a single trade.
- This is the **same order of magnitude as SPY Safe's own worst-case single-trade tail**
  (Rule 6's 30% per-trade allocation cap × the same -50% catastrophe stop = 15% of equity) —
  tickers is not structurally riskier per-trade than the SPY core arm it copied its exit ladder
  from, at these dollar amounts.
- The **real macro backstop** is the parent prereg's `EARLY_KILL_per_arm`: cumulative realized
  loss ≥3% of starting equity before the 20-day/30-fill minimums are met flips that arm to
  `shadow_only` immediately. That threshold, not the daily 1% figure, is what actually caps
  how much of the lane's capital day-one-style outcomes can consume before the experiment is
  paused for review.

## What shipped from this review (documentation only, zero behavior change)

Two **stale doc-string** fields in `automation/state/tickers/params.json#risk` were corrected
(pure `_`-prefixed comment fields — verified via `git diff` that zero numeric/behavioral keys
changed):

1. `_cap_note` said "5% of equity" / cited a $100K-account example — leftover from *before*
   the 2026-09-04 03:5x ET $5,000-equity correction that updated its sibling field
   `_per_trade_risk_cap_doc` to 30%/$5K but missed this one. Corrected to match.
2. `_kill_doc` said "~$1,000 on $100K paper" — same stale-sibling bug, corrected to
   "~$50 on the real $5,000 accounts" plus the day-one evidence and conclusion above.

## What did NOT ship, and why

**No numeric parameter changed.** Two candidate fixes exist and both are explicitly gated:

- **Raise `daily_loss_kill_switch_pct`** to a value that reflects the real worst-case tail
  (e.g. ~15%, matching SPY Safe's own per-trade tail) — the params file's own prior comment
  already labels this "a risk expansion" and the standing freeze doctrine says risk expansions
  wait for the 2026-10-30 checkpoint, regardless of file (this file is not on the frozen-path
  list, but the *expansion* rule is a project-wide default, not a per-file one). **Deferred to
  10-30.**
- **Lower `per_trade_risk_cap_pct` further** to shrink dollar exposure while keeping
  `max_contracts: 3` fixed (per the weekend plan's explicit instruction) — shown above to be
  mathematically incompatible with the current $5,000 equity tier: reaching a true 1%-consistent
  ceiling (~$0.33 max affordable premium) would refuse nearly the entire 9-name universe as
  `SIZE_BELOW_MIN`, defeating the point of the lane. **Not recommended at this equity tier;
  revisit only if/when equity grows.**

n=3 (one fill per arm, one day) is also far too thin to tune anything here even if it were not
gated — this review closes the *documentation* gap the audit surfaced, not a numeric one.

## Bottom line

Weekend-plan item 3 ("pre-register... in writing") is answered: **no urgent action needed now.**
The lane's real risk posture is sane and comparable to SPY Safe's own per-trade tail; the
mismatch was a stale comment, now fixed. The one open, genuinely gated decision (raise the kill
threshold to be honestly labeled) is filed for the 2026-10-30 checkpoint, not before.

**Revert:** `git revert <this commit>` (two `_`-prefixed doc-string fields in
`automation/state/tickers/params.json` + this file — zero trading-path behavior affected).
