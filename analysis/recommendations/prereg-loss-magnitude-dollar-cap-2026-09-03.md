# FROZEN PREREG — dollar-denominated per-position loss cap vs. the book's right tail

**rule_id:** `loss-magnitude-dollar-cap-2026-09-03`
**status:** `FROZEN_PREREG` — no sweep code exists yet; see `build_step` below. Do NOT tune sizing knobs looking for a good number (queue item's own instruction, restated as a hard gate in §5/§6).
**frozen_at_et:** 2026-09-03 04:41 ET (Thursday EDT, `et_clock.py` verified `market_hours=False` at freeze time)
**filed_by:** Sonnet, `automation/overnight/queue.md` item `LOSS-MAGNITUDE-AND-SIZING-IS-THE-UNTESTED-AXIS` (HIGH, filed 2026-08-23 Opus adjudication, THREAD not finding)
**parent_finding:** the two-tailed concentration fix (commit `0a51b817`) — bear −$16.71/tr flips to +$397 at drop-worst3; bull +$2.45/tr flips to −$1,455 at drop-top3. The deficit is carried by a handful of extreme trades, not a broad bleed. Entry selection (lever a) and stop tightening (lever b) are both adjudicated dead 2026-08-23; sizing the extreme trades smaller (lever c) has never been tested on this book.
**scope:** THIS prereg governs ONLY a per-position dollar loss cap applied via sizing. It does NOT re-open entry selection or stop tightening (both closed 2026-08-23) and it is NOT the `loss_armed_budget_shadow.py` daily-premium-budget shadow (a different mechanism — a same-day realized-P&L kill switch on NEW entries, not a per-position sizing cap; see §0 for why the two must not be conflated).

---

## 0. What is already live — verified this session, quoted

Three dollar-denominated risk controls shipped 2026-08-29 (`PREREG-TIGHT-LADDER-2026-08-28.md`) and are live on `automation/state/params.json` today (core account `safe-2`; `aggressive/params.json` carries the bold-2 mirror):

1. **`daily_loss_kill_switch_dollars`: 400** — params.json line 286. Doc string (`_daily_loss_kill_switch_dollars_doc_2026_08_29`, line 287): *"ALONGSIDE `daily_loss_kill_switch_pct` above — ADDS a third, independent KILL_SWITCH trigger in `risk_gate.check_order`; does NOT remove or weaken the existing pct-based trigger."* This is a **daily** stop, not a per-position cap.
2. **`_max_contracts_per_entry_doc_2026_08_29`** (params.json line 95): *"PREREG-TIGHT-LADDER-2026-08-28.md S2 control #1: '3 minimum, 5 maximum'."* Consumer: `backtest/lib/risk_gate.py::cap_entry_qty` (pre-check, clamps qty DOWN, never up), called from both `heartbeat_core.py#_execute` and `fleet_executor.py#finalize` before `risk_gate.check_order`.
3. **`_max_position_dollars_doc_2026_08_29`** (params.json line 284): *"hard dollar cap per position: $1,000 ... ADDITIONAL to per_trade_risk_cap_pct above, NOT a replacement — both bind, tighter wins."* Same consumer (`cap_entry_qty`).
4. Draft doctrine text for CLAUDE.md Rules 5/6 (not yet applied — `RULE9-DOC-PASS-2026-09-05-DRAFT.md` §6, scheduled for the 2026-09-05 Saturday doc pass): Rule 5 gains *"The live floor is the tighter of the % kill and the $400/day cap"*; Rule 6 gains *"max 5 per entry, max $1,000 per position — the tighter of the % cap and these $ caps wins."*
5. The existing −50% catastrophe cap (v15.3 chart-stop-primary, validated-KEEP) bounds a position's loss to −50% of its own premium spend — at the live $1,000/position ceiling that is a ~$500 worst case per position, but **the catastrophe cap is a percentage-of-premium bound, not an independent dollar floor**; it and the $1,000 position cap compound (a $1,000 position's catastrophe-capped loss is ~$500; a $400 position's is ~$200) rather than either one alone bounding the book's per-position dollar loss directly.

**What this means for THIS prereg:** the $1,000 max-position-dollars + 5-max-contracts ladder already caps *entry notional*. It does **not** cap *realized loss* independently of the catastrophe stop — a $1,000 position can still lose up to ~$500 today. Nothing today asks "would capping the realized per-position loss BELOW that ~$500 ceiling change the book's expectancy without gutting the right tail." That is the untested lever this prereg freezes.

**Forward evidence currently accruing (a related but DISTINCT mechanism, not to be conflated with this prereg's question):** `analysis/recommendations/loss-armed-budget-shadow-summary.json` (`setup/scripts/loss_armed_budget_shadow.py`) is running a FROZEN_PREREG_FORWARD shadow (`loss-armed-budget-forward-prereg-2026-08-28.json`) that blocks NEW entries once an arm's already-realized session P&L drops below zero, at three candidate thresholds (P-08/P-12/P-16 = 8/12/16% of start-of-day equity). As of `generated_at_et: 2026-09-02T17:10:01`, only 2 of the required 15 forward sessions have elapsed (`sessions_elapsed: 2`, `verdict_ready: false`); early reads (`delta_usd` +347/+260/+161 across the three candidates) are directionally positive but explicitly not yet gate-eligible (`F3_frequency_n_blocked_ge_10` and `F4_survives_dropping_best_session` both `false` on all three candidates at n=2 sessions). **This is a same-day entry-blocking mechanism keyed on cumulative session P&L — orthogonal to per-position sizing.** It is cited here only as the sibling shadow-ledger pattern this prereg's own forward component (§6) follows, not as evidence for the sizing question.

## 1. The question

Does capping the **planned maximum dollar loss per position** at $X change the book's expectancy without damaging the right tail that currently carries the book's positive trades?

**Cells (frozen, no others addable after data is seen):**

| cell | $X (planned max loss per position) | role |
|---|---:|---|
| CONTROL | ~$500 (the live-equivalent: $1,000 max-position-dollars × −50% catastrophe cap, unchanged from today) | current live shape, not a new intervention |
| A | $350 | mid cell |
| B | $250 | tightest cell |

Planned max loss is computed **at entry**, not realized: `entry_premium × qty × 100 × 0.5` (the −50% catastrophe-cap fraction, unchanged — this prereg does not touch the catastrophe cap's percentage, only whether qty is additionally shrunk so that percentage's dollar consequence is smaller). No cell scales UP a position (see §3).

## 2. Frozen population and IS/OOS split

**Population: engine-attributed real fills, 2026-07-08..2026-09-02, on the two CORE arms only** (`safe-2` and `bold-2` — CLAUDE.md's Account 1/Account 2, the arms this prereg's live-doctrine citations in §0 govern). Fleet arms (`safe-3`, `risky-1`, `risky-3`) are excluded from this prereg's frozen population — they run separate sizing tables (`fleet_executor.py::_qty_for`'s `position_sizing_tiers`) not gated by `cap_entry_qty` the same way, and mixing them would answer a different, unfrozen question.

**n, read fresh this session from `analysis/go-live-gate.json` (generated 2026-09-03T03:49:47) `criteria.statistical.per_arm`:**
- `safe-2`: `n_engine_trades: 90`, `n_trading_days: 31`
- `bold-2`: `n_engine_trades: 42`, `n_trading_days: 21`
- **combined core-arm population: n=132.** (Book-wide `n_engine_trades: 278` across `n_trading_days: 41` includes the three fleet arms and is NOT this prereg's population — cited in §0 only as provenance for the go-live-gate instrument.)

⚠️ **Unverified this session:** `go_live_gate.py`'s exact date-window boundaries for the `per_arm` statistical rollup were not independently re-derived (the file exposes `n_trading_days` and per-arm trailing windows for the *behavioural* criterion at lines 335-355, but the *statistical* `per_arm` block's own window start was not confirmed to equal 2026-07-08 exactly). The build step (§8) MUST independently re-derive its own population directly from `automation/state/fills-ledger.jsonl` (`attribution=='engine'`, arm ∈ {safe-2, bold-2}, date_et 2026-07-08..2026-09-02) rather than trusting go-live-gate.json's n as authoritative — the n above is cited as directional provenance, not as the frozen count. If the independently-derived n differs materially from 132, the build step reports both counts and does not silently prefer one.

**IS/OOS split rule (per playbook §4.5, chosen UP FRONT):** this study's "changed trades" are the positions whose planned qty would actually be reduced under cell A or B (i.e., positions whose planned max loss already exceeds $350/$250 at CONTROL sizing) — expected to be a MINORITY of n=132 (large positions only), almost certainly **< 33% of the population**. Per §4.5's rule (*"if the knob's expected changed-trade fraction is < 33% of the population ... prereg EQUAL-CHANGED-TRADE-COUNT buckets (`backtest/lib/canonical_battery.py::equal_count_buckets`, n_buckets=4) instead of calendar windows"*): **this prereg freezes EQUAL-CHANGED-TRADE-COUNT buckets, n_buckets=4, computed over the changed-trade subset only** — not fixed calendar windows. The build step must verify the actual changed-trade fraction once computed and record it in the output; if it in fact clears 33%, calendar windows (2026Q3 vs. trailing) may be used instead, per §4.5's own either/or, but the DEFAULT frozen here is equal-count buckets.

## 3. The counterfactual — scale DOWN only, never up

For every entry in the frozen population, recompute what qty **would have been placed** under each cell, using the SAME clamp mechanism the live code already uses — read fresh this session from `backtest/lib/risk_gate.py::cap_entry_qty` (lines 1134-1250):

- Planned max loss at proposed qty = `proposed_qty × premium × 100 × 0.5`.
- If that exceeds the cell's $X, qty is shrunk: `dollar_max_qty = int(max_dollars // (premium_f * 100.0))` (line 1228 — **floor division to a whole contract count**, quoted verbatim from the live function; this prereg's counterfactual reuses this exact formula with `max_dollars = 2 * cell_X` since `cap_entry_qty` bounds *notional*, not *catastrophe-capped loss*, so the study computes the qty that makes `qty × premium × 100 × 0.5 <= cell_X`, i.e. `max_dollars_equiv = 2 * cell_X`, then applies the identical floor-division formula).
- **Conflict rule (control #3, quoted from `cap_entry_qty` lines 1233-1250):** if the shrunk qty falls below `min_contracts`, the position is **SKIPPED entirely at that cell** ("conflict: min_contracts would violate ... a configured cap — SKIP rather than under-size below the ladder floor"), not force-sized down below the 3-contract ladder floor. The study must report `n_skipped_by_conflict` per cell as its own disclosed field — a cell that skips many of the book's most profitable large positions is not silently absorbed into the qty-shrink counterfactual; it is a distinct failure mode reported separately.
- **No cell ever increases a position's planned qty.** A position already under a cell's $X cap at its live qty is carried through unchanged (`capped_by_dollars = False` in `cap_entry_qty`'s own return contract).
- Realized P&L for the counterfactual is the recomputed-qty scaling of the position's ACTUAL exit price path (same entry/exit prices and times, only qty changes) — this study does not re-simulate a different exit; it re-sizes the realized one.

## 4. Right-tail-damage gate — ship-candidate only if ALL THREE hold

A cell is a **ship-candidate** only if, relative to CONTROL:

1. **Top-3 winners' dollar contribution shrinks by LESS than the bottom-3 losers' dollar contribution shrinks.** (`Δ(sum of top-3 winning trades' $)` in absolute value < `Δ(sum of bottom-3 losing trades' $)` in absolute value — i.e., the cap must cut more off the loss tail than it cuts off the win tail. This is the concentration check named directly by the parent finding and required by playbook §4.3's "a mean without a drop-topN is not a verdict.")
2. **Ex-best-day expectancy does not fall.** Recompute the book's per-trade expectancy dropping the single best trading day (same convention as `go_live_gate.py`'s `ex_best_day` statistical criterion) — must be >= CONTROL's ex-best-day expectancy.
3. **The day-level bootstrap PF CI-lower (2.5th percentile) does not fall.** Reuse `go_live_gate.py`'s own bootstrap machinery (`statistical_criterion`'s day-block bootstrap, `n_boot=20000`) on the counterfactual-resized daily P&L series — `ci_lower_2.5` for the cell must be >= CONTROL's `ci_lower_2.5`.

Any cell failing any one of the three is **NOT a ship-candidate**, full stop — no partial credit, no "2 of 3 is close enough."

## 5. Illusion guard — variance/Sharpe are DISCLOSURE only

Per the queue item's own warning (*"sizing is the single easiest way to manufacture a backtest illusion: shrink size, shrink variance, flatter Sharpe, same broken edge"*): **the study MUST compute and report Sharpe ratio and P&L variance/std-dev for every cell, but neither may appear in, or influence, the ship-candidate decision in §4.** They are reported in a clearly separate `disclosure_only` block in the output JSON. A cell that "improves Sharpe" while failing §4's three gates is **not** a ship-candidate — this rule exists specifically to block that exact failure mode.

## 6. Forward component — required before any 10-30 ship

Per playbook §4.9's forward-clock pattern (same shape as `day-throttle-shadow-ledger.jsonl` / `loss-armed-budget-shadow-ledger.jsonl`, cited in §0 above as the sibling pattern): **the in-sample cell that clears §4's ship-candidate bar must ALSO run as a forward SHADOW measurement (paper-verified, non-blocking — the live entry path is untouched) for >= 20 trading days before ANY sweep result may be proposed for a live sizing change.** The shadow ledger records, per candidate entry: proposed qty, cell-capped qty, whether §3's conflict-skip fired, and the realized P&L delta the cap would have produced — same measurement-only contract as `loss_armed_budget_shadow.py` (§0), not a live-order-affecting mechanism. Forward-clock start date is the date the shadow script first runs, not this freeze date.

## 7. Frozen verdict vocabulary

- **`SHIP-CANDIDATE`** — a cell that clears all three §4 gates on in-sample AND then clears the same three gates again on its own >=20-trading-day forward shadow (§6), independently re-tested (not the same window re-read twice).
- **`SHADOW-PENDING`** — a cell that clears §4 in-sample but has not yet accumulated >=20 forward trading days.
- **`REFUTED`** — a cell that fails any one of §4's three gates, in-sample or forward.
- **`UNDERPOWERED`** — the changed-trade subset (§2) is too small to bucket meaningfully (fewer than ~20 changed trades total across n_buckets=4, i.e. <5 changed trades per bucket, mirroring this repo's existing >=5-changed-trades-per-window floor from playbook §4.5's own worked example) — reported as its own verdict, never silently folded into REFUTED or SHIP-CANDIDATE.
- No other verdict word may be used in this study's output.

## 8. `build_step` — the script this prereg requires, which does NOT exist yet

**No code has been written for this prereg.** Verified this session: no file matching this name exists anywhere in the repo.

```json
{
  "build_step": {
    "file": "backtest/tools/loss_magnitude_dollar_cap_sweep_2026_09_03.py",
    "symbol": "run_dollar_cap_sweep",
    "must_contain": [
      "independently derives the frozen population from automation/state/fills-ledger.jsonl (attribution=='engine', arm in {safe-2, bold-2}, date_et 2026-07-08..2026-09-02) -- does NOT trust analysis/go-live-gate.json's n as authoritative, per section 2's unverified-window caveat; reports both its own n and go-live-gate.json's n=132 side by side",
      "reuses backtest.lib.risk_gate.cap_entry_qty's exact floor-division formula (int(max_dollars // (premium * 100.0))) for the counterfactual qty computation -- does NOT reimplement or approximate the rounding rule a second way",
      "implements the section-3 conflict rule verbatim: a position whose cell-capped qty would fall below min_contracts is SKIPPED at that cell (n_skipped_by_conflict reported per cell), never force-sized below the ladder floor",
      "never increases qty above the position's actual live qty at any cell -- CONTROL cell reproduces the live realized P&L exactly (regression-testable: sum(control_pnl) == sum(realized_pnl) over the population)",
      "computes the section-4 right-tail-damage gate as three independently reported booleans per cell (top3_vs_bottom3_asymmetry_pass, ex_best_day_expectancy_pass, bootstrap_ci_lower_pass) plus the combined ship_candidate boolean -- does NOT collapse them into a single opaque score",
      "reuses go_live_gate.py's day-block bootstrap (statistical_criterion's n_boot=20000 mechanism) for the ci_lower_2.5 computation -- does NOT reimplement bootstrap resampling a second way",
      "computes Sharpe and P&L variance/stddev per cell into a separate top-level disclosure_only JSON key that the ship_candidate boolean never reads from -- code-enforced separation, not just a comment",
      "buckets the changed-trade subset (positions where cell-capped qty < live qty) via backtest.lib.canonical_battery.equal_count_buckets(n_buckets=4) as the DEFAULT split per section 2, and separately reports the actual changed-trade fraction so a future re-run can confirm whether calendar windows would also have been eligible per playbook 4.5",
      "emits verdicts using ONLY the section-7 frozen vocabulary (SHIP-CANDIDATE / SHADOW-PENDING / REFUTED / UNDERPOWERED) -- no other verdict string permitted in output",
      "is a read-only backtest study: writes ONLY to analysis/recommendations/ output files; never edits params.json, aggressive/params.json, risk_gate.py, heartbeat_core.py, or fleet_executor.py",
      "$0 cost -- reuses existing fills-ledger.jsonl and go-live-gate.json data already on disk; no new OPRA fetch, no new paid data source"
    ]
  }
}
```

## 9. Timing — not before 2026-10-30

**This prereg's SHIP-CANDIDATE verdict, even if reached, may not be proposed for a live params.json change before 2026-10-30, and only as a KILL-TYPE reduction if it reduces size** — i.e. any live change this study could ever justify is a further TIGHTENING of sizing (lower max_position_dollars-equivalent, or a new explicit per-position-loss-dollar cap), never a loosening, and never before the PREREG-TIGHT-LADDER-2026-08-28.md 40-day forward clock (closing 2026-10-30, per `analysis/go-live-gate.json` line 388's `window_end`) has itself completed. This is consistent with the September config-freeze (CLAUDE.md / `setup/hooks/doctrine.py FREEZE_END`) already in force over this exact period.

## 10. Falsification note

The honest way this prereg dies without a SHIP-CANDIDATE: the changed-trade subset is too small to bucket (`UNDERPOWERED`), OR every cell that tightens the loss tail also cuts the win tail by MORE (fails §4.1) — which would mean the "handful of extreme trades" carrying the deficit are the SAME handful carrying the book's positive tail, and sizing cannot separate the two without re-opening entry selection (lever a, already exhausted 2026-08-23). That outcome is itself the answer to the queue item's THREAD, not a failure of this study.
