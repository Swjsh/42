# Lesson candidate: "N fills, 0% WR" over-counts independence -- same-day re-entries and
correlated same-day-side setups are not N independent trials

**Filed:** 2026-07-25 (conductor, AFTERHOURS), ZERO-FOR-TWELVE-POSTMORTEM follow-up (closes
the "NOT DONE" next step named by two earlier fires today).

**Symptom:** `vwap_continuation` (7 fills, 0% WR, -$204) and `vix_regime_dayside` (5 fills, 0%
WR, -$153) were DISARMED 2026-07-25 on the framing "0-for-12 combined at a claimed ~55-64% WR is
p<1% -- a falsification of the validation pipeline, not two unlucky setups."

**What the day-cluster actually shows** (`journal/trades.csv`, verified this fire): the 12 CSV
rows are **4 distinct calendar days** (2026-07-16, 07-20, 07-21, 07-22) and **4 distinct
(day, side) buckets**. Two mechanisms collapse the count:
1. **Same-day re-entries / same-signal leg splits.** 2026-07-20 vix_regime_dayside logged 4 rows,
   all side=C, two sharing the EXACT same entry timestamp (09:54:19) -- almost certainly a
   TP1+runner leg split of ONE entry, not two bets. 2026-07-21 vwap_continuation logged 2 rows
   both at 10:11:29, same pattern.
2. **Cross-setup correlation via a shared classifier.** On 2026-07-21, `vix_regime_dayside` AND
   `vwap_continuation` BOTH fired PUT -- confirmed (earlier fire today, grep-verified) that both
   setups derive `side` from the IDENTICAL `session_vwap_asof` day-trend-side function
   (`autoresearch/infinite_ammo_discovery.py`, imported verbatim by both). A wrong day-trend read
   is not two independent setup failures; it is one wrong classification wearing two setup names.

**Root cause:** "N fills" (rows in a fills ledger) silently assumed independence. It is a row
count, not a trial count. Under a naive per-trade binomial framing, 0-for-12 at 55-64% claimed WR
reads as p<1% (extraordinary). Under the honest ~4 independent day-outcomes framing, the same
claimed WR gives roughly (1-0.55)^4 to (1-0.64)^4 = ~1.7%-4.1% -- still worth investigating, but
no longer a clean "the validation pipeline is falsified" signal on its own. The DISARM decision
itself is not reversed by this (other caveats -- L174 day+side selection, small n -- still apply
independently), but the STATISTICAL FRAMING that made it feel like p<1% certainty was inflated by
~3x on trial count alone.

**Fix (shipped this fire, commit 9ad0a907):** `trade_to_learn_digest.compute_since_arm()` now
reports `n_distinct_days` / `n_distinct_day_side_buckets` alongside `n_fills` per setup, and a new
top-level `cross_setup_same_day_side` field flags when 2+ armed setups fire the same (date, side)
-- generalizes past this one pair to any future setup sharing a classifier. `format_lines()` warns
inline so a since-arm digest never again reads "N fills, X% WR" as N independent trials without a
visible caveat.

**Generalizable rule (fold target: C4 disclosure / C13 confidence-tiers, or a new sibling):** any
"since-arm" or "since-live" cumulative fills digest MUST distinguish trial count (rows) from
independent-evidence count (distinct day, or distinct day+side, or distinct underlying
classification) before that digest is used to make a disarm/keep call. A losing STREAK measured in
row-count can be a losing streak of a handful of correlated DAYS wearing a many-trial costume --
and two setups sharing an entry classifier will amplify a single bad day-read into what looks like
independent multi-setup confirmation of "this doesn't work."

**Downstream (do not over-claim):** this does NOT itself prove the disarmed setups ARE profitable
-- it only corrects how surprising the 0-for-12 evidence should be read as. The still-open L174
"day+side selection, not independent trials" historical-validation caveat is a SEPARATE, still-live
question (quantifying it needs the OOS(2026) signal population, not the live sample -- flagged as
a further NOT-DONE step if this thread is picked up again).
