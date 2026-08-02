# PREREG — ONE-POSITION-AT-A-TIME CONSTRAINT COST (measurement, no ship/kill gate)

**Frozen:** 2026-08-02 03:30:56 ET (Sunday, market closed; `setup/scripts/et_clock.py` read fresh)
**Committed BEFORE the runner exists** — freeze order is git-provable: this file's commit
predates `backtest/tools/one_position_constraint_cost_2026_08_02.py` in history.

---

## ⛔ MEASUREMENT ONLY — read this first

This lane **ships nothing and arms nothing**. It quantifies the cost of a RISK-POSTURE
constraint (how many contracts can be open at once) so J can make an informed decision.
Concurrency is J's call, not this session's — it touches Rule 6 (per-trade risk cap) and
Rule 5 (daily kill switch). There is **no pass/fail gate** here, no auto-ratify path, no
recommendation to flip anything on. The deliverable is a number and a risk analysis, framed
as a decision input. If the honest read is "the constraint is correct as-is," that is a
valid, real result — reported plainly, same as a NULL verdict on any A/B.

Because there is no ship hypothesis to freeze, what this prereg freezes is the **method** —
population, the concurrency-admission algorithm, and the report cuts — so the definitions
cannot drift toward whichever answer looks more interesting once the numbers are in.

## Provenance question (task step 1, frozen approach)

Read CLAUDE.md's 10 rules verbatim + `setup/scripts/heartbeat_core.py`'s own code comment at
the `fb.is_flat_spy_options(creds)` gate (~line 1895) + `markdown/0dte/risk-rules.md`. Quote
all three sources exactly; do not paraphrase-then-argue. Rule 6 is textually a PER-TRADE cap
("30% of account equity" / "50% of account equity" — CLAUDE.md, `automation/state/params.json
#per_trade_risk_cap_pct` / `aggressive/params.json#per_trade_risk_cap_pct`), not a portfolio
cap; nothing in Rule 6's text bans a second concurrent position each independently within its
own cap. Classify the constraint as (a) direct rule requirement, (b) conservative
implementation choice protecting a rule's intent, or (c) unexamined default — using the
code's OWN cited rationale plus `daily_loss_kill_switch_pct` vs `per_trade_risk_cap_pct`'s
numeric ratio in both params files as physical evidence of what the constraint actually
protects. State the ratio finding plainly, whichever way it comes out.

## Population (frozen)

- **Bold**: `backtest/tools/bold_fullhist_replay.py#replay_population(block_elite_bull=True,
  qty_mode="fixed", min_contracts=5)` — the CURRENT LIVE core-Bold candidate population,
  reused verbatim (import, zero modification), already carries `exit_time_et`. Window
  2025-01-02..2026-07-22, `BOLD_LIVE_EQUITY=1197.52` (live-verified 2026-08-01/02).
- **Safe**: a NEW hand-built loop (`_replay_safe_population`, this study's own runner) that
  reuses `engine_fullhist_replay.py`'s `SAFE_BASE_LIVE` / `build_ribbon_lookup` /
  `ribbon_tick_df_for` / `naive_dt` **verbatim, unmodified** (import only — this measurement-
  only lane does not edit that already-shipped, already-anchored file) and adds the ONE field
  it discards today: `exit_time_et` (already computed by `walk_exit_manager`'s `WalkResult`,
  never captured into the row dict). Same window, `SAFE_EQUITY=1746.75` (CLAUDE.md
  2026-07-11 live-verified, the same figure `engine_fullhist_replay.py` already uses — most
  current on record for Safe as of this freeze).
- Both populations are the **CURRENT LIVE fixed-floor sizing shape only** (Bold
  `min_contracts=5`, Safe `min_contracts=3`) — the REJECTED adaptive-sizing variant
  (`bold_adaptive_sizing_2026_08_02.py`, NULL verdict, three iterations concluded tonight) is
  explicitly OUT of this population; mixing it in would confound the concurrency measurement
  with a separately-adjudicated, already-killed sizing change.
- Disclosed asymmetry (pre-existing, not introduced here): Bold's population excludes
  risk-cap-unaffordable signals (`resolve_bold_qty` returns `None`); Safe's inherited loop
  applies no such filter (matches the already-shipped `engine_fullhist_replay.py`'s own
  modeling choice — `qty=int(t.qty)`, always 3, the `DEFAULT_QTY` coincidence its sibling
  tool's docstring already discloses for Safe).

## Frozen definitions

- **Concurrency-admission, `_sequential_admit_concurrent(rows, K)`**: process signals in
  chronological `entry_time_et` order; admit a signal iff fewer than `K` previously-admitted
  positions are still open (`exit_time_et > this signal's entry_time_et`) at its arrival.
  `K=1` is the CURRENT live constraint and must be byte-parity-checked against the
  already-shipped `bold-adaptive-sizing-2026-08-02.json#control_sequential` figures
  (n=153, $+7,578.40) before anything downstream is trusted. Unresolved-trade convention
  (missing `exit_time_et`) inherited unchanged from `_sequential_admit`: occupies its slot
  through 16:00 ET of its own entry day.
- **Monotonic superset property**: `admitted(K) ⊇ admitted(K-1)` for the same chronological
  input under this rule (proof: an independently-coded "cascading servers" formulation, where
  server 1 always reproduces `admitted(1)` alone regardless of servers 2..K, is cross-checked
  against the primary algorithm on the REAL population, not just a synthetic fixture, in the
  guard file). This is what makes "refused cohort" and "gained cohort per concurrency step"
  well-defined and non-overlapping across levels.
- **Refused cohort (opportunity cost, task step 2)**: `candidate_rows \ admitted(1)` — signals
  that exist in the current live candidate population but never got a slot. Reported: n, total
  P&L, WR, drop-best, **recent-25 FIRST** (J's dynamic-market/recency doctrine,
  `feedback_dynamic_market_recency_over_aggregate_2026_07_31`).
- **Capital at risk / notional**: `entry_premium × qty × 100` per open position — the SAME
  definition `resolve_bold_qty` / `risk_gate`'s own RISK_CAP check already uses for Rule 6,
  reused for consistency rather than invented fresh. Walked chronologically over the
  ADMITTED set at each concurrency level; peak simultaneous sum + peak simultaneous count
  recorded (count must never exceed `K` — a self-consistency guard on the admission
  mechanism itself).
- **Kill-switch breach (task step 3)**: day-level REALIZED P&L (sum of `dollar_pnl` for all
  admitted trades whose `entry_time_et` falls on that calendar date) compared against
  `-equity × daily_loss_kill_switch_pct` (static equity, non-compounding — this repo's
  established full-window-study convention, same as every other `*_fullhist_replay.py` tool).
  **Disclosed as a LOWER BOUND, not the true intraday risk**: `risk_gate`'s own kill-switch
  trigger (b) reads live mark-to-market `equity <= start_of_day_equity × (1 -
  daily_loss_kill_switch_pct)` at the moment of a NEW entry attempt — a continuous intraday
  check this end-of-day-realized proxy cannot reproduce. Under concurrency > 1, simultaneous
  open exposure could plausibly trip the REAL live gate mid-session even on a day whose
  END-OF-DAY realized total looks fine — so this study's breach counts likely UNDERSTATE risk
  at K>1, and that direction of error is disclosed explicitly, not hedged away.
- **Slot-turnover (task step 4, the cheaper adjacent question)**: for each refused-at-K=1
  signal, identify the SINGLE admitted-1 trade whose open interval contains its arrival (by
  construction under K=1, exactly one exists — asserted, not assumed), compute
  `gap_minutes_needed = occupant.exit_time_et − refused.entry_time_et` (how much earlier the
  occupant would need to exit) and `gap_as_pct_of_occupant_hold`. Cross-referenced
  (descriptively, NOT row-joined — different dataset, different population, disclosed) against
  `analysis/pain-ledger/mae-mfe.json`'s real-fills `time_to_mfe_min` vs `hold_minutes` for
  winners, as corroborating/directional evidence only.

## Frozen report cuts (ALL reported, none dropped)

1. Per arm (Safe, Bold) × concurrency level (1, 2, 3): n admitted, total P&L, WR, drop-best,
   **recent-25 first**, gained-vs-prior-level cohort.
2. Refused-at-K=1 cohort: n, total P&L, WR, recent-25, drop-best.
3. Risk: peak simultaneous notional + count per level; day-P&L series; kill-switch breach
   count/days per level vs K=1 baseline; worst single day per level.
4. Slot-turnover: gap-minutes-needed distribution (median/p25/p75) + gap-as-%-of-occupant-hold
   distribution; pain-ledger cross-reference (descriptive).
5. Provenance verdict (a/b/c) with the exact quoted rule text, code comment, and the
   per-trade-cap : kill-switch ratio finding.

No BH-FDR / significance testing — this is a population-level accounting exercise (opportunity
captured vs risk incurred at each concurrency level), not a hypothesis test with a p-value. No
ship gates are frozen because nothing ships from this lane.

## Disclosed limitations (frozen now so they can't become excuses later)

- Static, non-compounding equity for both arms (this repo's established full-window-study
  convention — the numbers are a WHAT-IF snapshot at current equity, not a compounding curve).
- Kill-switch breach counting is an end-of-day-realized proxy — a disclosed LOWER BOUND on
  real intraday risk at K>1 (see above).
- Safe's candidate population carries no risk-cap-affordability exclusion (inherited from the
  already-shipped `engine_fullhist_replay.py`); Bold's does. Pre-existing asymmetry, not
  introduced by this study.
- Pain-ledger cross-reference uses a SEPARATE, much smaller (n≈160), real-fills-only dataset
  spanning 22 distinct dates — descriptive corroboration only, never row-joined against the
  386-day synthetic-population backtest.
- This does not model `structure_veto_enabled`, PDT/settlement, or any runtime/state-dependent
  `risk_gate` check — same disclosed gap every `*_fullhist_replay.py` tool in this repo already
  carries.

## Deliverables bound to this prereg

1. `backtest/tools/one_position_constraint_cost_2026_08_02.py` (runner) +
   `analysis/deep-research/ONE-POSITION-CONSTRAINT-COST-2026-08-02.json` (raw output).
2. `backtest/tests/test_one_position_constraint_cost_2026_08_02.py` (guards, RED-proofed):
   admission-mechanism synthetic fixtures, cascading-servers cross-check on the REAL
   population, monotonic-superset assertion, kill-switch/notional calculators on synthetic
   fixtures with known answers, and the K=1 parity anchor.
3. `analysis/deep-research/ONE-POSITION-CONSTRAINT-COST-2026-08-02.md` — the narrative
   deliverable: opportunity cost, risk cost, kill-switch impact, slot-turnover finding, and a
   recommendation FRAMED AS J'S DECISION with the number attached, never an action taken.
