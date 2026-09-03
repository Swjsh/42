# DATA pre-registration — backfill `cf_*` exit counterfactuals at POSITION level

**rule_id:** `exit-counterfactual-backfill-data-2026-09-03`
**status:** `FROZEN_PREREG` (DATA prereg — no code exists yet; see `build_step` below)
**frozen_at_et:** 2026-09-03 04:31 ET (Thursday EDT, `et_clock.py` verified `market_hours=False` at freeze time)
**filed_by:** Sonnet, `automation/overnight/queue.md` item `EXIT-COUNTERFACTUAL-BACKFILL-DATA-PREREG` (MED, filed 2026-08-23 after the exit study was REFUTED)
**parent_finding:** `analysis/deep-research/PROFITABILITY-ORDER-2026-08-23.md` §5 (the exit-policy `beats_null` hypothesis was REFUTED on every computable cut; §5e names this exact DATA prereg as "what replaces it")
**shadow_only:** true — this file authorizes ZERO code beyond the one backfill script named below. It changes no live order path, no exit shape, no params key. It is a data-availability freeze, not an intervention.

---

## 0. Why this is a DATA prereg, not an exit-intervention prereg

⛔ Per the parent finding's own instruction (§5c): **"Directionally it is dead. Do NOT write an exit-intervention prereg."** The `beats_null` hypothesis (does a different exit policy beat the realized one) was tested on the only loser-inclusive population available (`analysis/autopsies/*.jsonl`, n=263) and refuted on G2 (drop-top3 flips +$79.03 → +$1.60), G3 (drop-best-2-days sign-flips to −$187.59), and G5 (day-block bootstrap P(Δ≤0)=0.385, fails the 0.05 bar). It escaped only *formal* refutation because the frozen population (`journal/trades.csv`'s `cf_time_stop_pnl`/`cf_high_water_pnl` columns) was never measurable — 3 of 508 rows populated, 0 of 493 in-window, and even those 3 are untrustworthy (one has `cf_time_stop_pnl == dollar_pnl` exactly; one has `cf_high_water (−770) < cf_time_stop (+410)`, impossible for a high-water bound).

This file freezes the **measurement**, not a hypothesis about exits. Only after coverage clears the 80% floor below does any beats-null question get asked again — and even then, as a fresh, separately-frozen hypothesis prereg, not this one.

## 1. Verified data-integrity defect (re-confirmed this session, not re-derived from memory)

Both `cf_*` writers were re-read fresh this session and still emit the literal empty string:

```
setup/scripts/fleet_journal_bridge.py:671:        "cf_time_stop_pnl": "",
setup/scripts/fleet_journal_bridge.py:672:        "cf_high_water_pnl": "",
```

```
backtest/autoresearch/webull_winner_journal.py:414:        "cf_time_stop_pnl": "",
backtest/autoresearch/webull_winner_journal.py:415:        "cf_high_water_pnl": "",
```

`journal/trades.csv`'s header carries both column names (`cf_time_stop_pnl`, `cf_high_water_pnl` — the complete `cf_*` family, verified via the CSV header, no third column exists). Nothing on disk today computes either column. This confirms the parent finding's defect still stands unpatched as of this freeze.

## 2. Population — POSITION level, not exit-leg level

**Unit of analysis: one POSITION (`arm`, `symbol`, `date_et`), FIFO-matched across ALL its exit fills — never one exit leg.** This is the specific, verified reason the columns were never computable: **124 of the 250 in-window positions (49.6%) closed in more than one exit fill** (partial TP1 + runner, multi-leg scale-outs, etc.), so a per-exit-leg counterfactual has no single well-defined "what if we'd held instead" answer — the counterfactual question ("what would this POSITION have realized under a different exit policy") is only coherent once fills are reconstructed into positions first.

The repo already has exactly ONE canonical position-reconstruction implementation — reuse it, do not fork a second one:
`backtest/tools/exit_shape_parity_study.py::reconstruct_positions` (already the single source of truth per `pain_ledger.py`'s own header doc and `trade_autopsy.py::load_engine_positions`).

**Source population:** `automation/state/fills-ledger.jsonl`, `attribution=='engine'`, option BUY fills reconstructed into positions via `reconstruct_positions`, restricted to the in-window date range the eventual question freezes at run time (do not silently widen or narrow the window post-hoc — if the window needs to move, this prereg is VOID and a fresh one is written, same `no_peeking_rule` convention as this repo's other forward preregs).

**Bars:** real Alpaca OPRA 1-min bars only, via the SAME fetch path every other position-level backfill in this repo uses — `backtest/tools/exit_shape_parity_study.py::fetch_option_bars` (wrapped by `trade_autopsy.py::fetch_bars_cached` for on-disk caching). **No synthetic pricing path.** A position with no OPRA bars, no exit-eligible bars, or a non-positive entry price is excluded AND counted (same disclosure convention as `analysis/pain-ledger/mae-mfe.json`'s `n_no_bars`/`n_no_window`/`n_bad_entry` fields) — never silently dropped.

**Entry convention:** entry+1 (entry bar excluded), per `ENTRY-BAR-CONVENTION-RULING-2026-07-25` — the SAME convention `pain_ledger.py` already uses (`setup/scripts/pain_ledger.py::holding_window`). Reuse that function; do not re-derive entry+1 a third time (there is exactly one entry+1 implementation in the repo per that module's own header doc — extend it, don't fork it).

## 3. The null — TRULY unmanaged, no premium cap

The parent finding's §5d is explicit and is FROZEN here verbatim as the defining constraint: **no implementation on disk today defines an unmanaged null.** Measured on identical rows, the three candidate "null" shapes disagree by 3.5x:

| shape (from `setup/scripts/trade_autopsy.py`'s `COUNTERFACTUALS`) | per-trade Δ |
|---|---:|
| `no_stop_ride` | +$22.86 |
| `wide_stop_-50` (the −50% catastrophe cap) | +$65.40 |
| `hold_to_time` | +$79.03 |

The −50% catastrophe cap is **graveyarded VALIDATED-KEEP** doctrine (v15.3 chart-stop-primary; the cap is a real, shipped, kept intervention). A null that has the validated cap sitting inside it is not a null — it is "compare our exit to a DIFFERENT validated intervention," which answers a different question than "did managing the exit at all help."

**Correction against a tempting shortcut:** `trade_autopsy.py`'s existing `COUNTERFACTUALS["hold_to_time"]` shape (the one that produced the $79.03/tr figure in the table above) is **NOT** the true null this prereg requires — it still carries `premium_stop_pct: -0.95` (a "near-disabled" stop, deliberately kept as an `ORACLE`/`DIAGNOSTIC_COUNTERFACTUALS`-only shape per that module's own 2026-08-06 fix comment, precisely because an unbounded-upside near-stopless shape wins "best counterfactual" on every trend day by construction). Reusing it unchanged would repeat the exact contamination §3's table exists to document — a stop, even a wide one, is still management.

**Frozen definition for this backfill: `premium_stop_pct` ABSENT (not `-0.95`, not `-0.50`, not any numeric value — the stop check is skipped entirely), no TP ladder, no chart-stop, no trailing lock. The position holds the FULL entry quantity from entry+1 to the 15:50 ET hard mechanical time-stop and closes there, full stop.** This is `cf_time_stop_pnl`'s intended meaning read literally: the counterfactual P&L of a position that was never managed at all before the mechanical end-of-day close — a new, stricter shape than anything currently in `trade_autopsy.COUNTERFACTUALS`, to be added there (or defined locally in the new backfill script) under an explicit new key (e.g. `"true_unmanaged_hold"`), never aliased to the existing `hold_to_time` entry. `cf_high_water_pnl` backfills alongside it as the position's best attainable exit within its own OPRA-observed high-water mark (MFE-anchored, same `excursion_metrics` convention `pain_ledger.py` already computes) — reported for completeness, never substituted for the null.

## 4. `stop_mode` — sourced from the decisions ledger per position (already exists, reuse it)

The parent finding's §5d names this as un-computable "from either source" (`trades.csv` nor `analysis/autopsies/`). That is correct for those two files, but **the repo already has TWO stop_mode-recovery implementations that read closer to the source of truth — reuse the stronger one, do not build a third:**

1. **`setup/scripts/pain_ledger.py::recover_stop_mode_from_exit_trace` + `stop_fields`** (preferred). Reads the engine's own `exit_pass[]` tick history per position from `automation/state/core-decisions.jsonl`, recovering `stop_mode` from either the tick-logged value (agreement across all non-null ticks) or a structural inference (`level_hit`/`chart_stop` action implies `state.stop_mode == "structure"`). Already runs nightly and already stamps a `stop.stop_mode`/`stop.stop_mode_source` block on every position in `analysis/pain-ledger/mae-mfe.json` (verified this session: 394 positions, each carrying a `stop` sub-object with `stop_mode`, `stop_mode_source` ∈ `{placement, exit_trace, unrecoverable}`, `stop_basis`). **This is the per-position, decisions-ledger-sourced field the queue item asks for — it already exists, it is just never joined onto `trades.csv`/`analysis/autopsies/`.**
2. **`setup/scripts/trade_autopsy.py::lookup_stop_mode`** (weaker, DO NOT use as primary). Reads a fleet arm's *live* `exit-state.json`, which `exit_actuator` deletes once a position is fully flat — routinely `None` for same-day-closed positions by the time it runs, and core arms (`mcp_heartbeat` execution) aren't covered at all (different state mechanism). Named here only so a future author doesn't reach for it and get silent low coverage.

**Frozen choice: join `stop_mode` via `pain_ledger.py`'s functions (or by reusing `analysis/pain-ledger/mae-mfe.json`'s already-computed `stop.stop_mode` field directly, keyed on `(arm, symbol, date_et)`) — not `trade_autopsy.lookup_stop_mode`.**

## 5. Coverage bar — >=80% of in-window positions, gate BEFORE any question

Verbatim from the parent prereg's own precedent (`exit_policy_beats_null_2026_08_23.py`'s `G8_coverage_honesty` — this repo's existing 80% floor for exactly this data family, reused unchanged): **coverage = (in-window positions with a usable backfilled `cf_time_stop_pnl` AND a resolved `stop_mode`) / (total in-window positions).** If coverage < 80%, the backfill run reports `UNDERPOWERED` and **no beats-null, G6, or any other question may be asked of that run** — this is a gate, not a caveat appended after a number is already reported (the exact §5c mistake this prereg exists to prevent from recurring).

## 6. Frozen list of questions this backfill will later be eligible to answer

None of these may be run until §5's coverage bar clears. Listed now, frozen, so a future session cannot silently narrow or widen the question list after seeing the data (`no_peeking_rule`, same convention as `vwap-family-killcheck-prereg-2026-08-18.json` and this repo's other forward preregs):

1. **The original beats-null question, re-askable honestly**: on both CONTROL-winners and CONTROL-losers, does hold-to-15:50 (the TRUE unmanaged null, §3) beat the realized managed exit, at >=80% coverage? (Verbatim carry-forward from `PROFITABILITY-ORDER-2026-08-23.md` §5e.)
2. **G6 — Simpson's-paradox stratification by `stop_mode`.** The exact check that unmasked the fake "bear stops fire at −8% vs bull −43%" finding (§3 of the same parent doc, resolved as a stop_mode-mix artifact, not a real asymmetry). This backfill is what makes G6 computable for the exit-null question for the first time.
3. **G2 (drop-top3) / G3 (drop-best-2-days) / G5 (day-block bootstrap)** on the corrected, position-level, true-null data — re-running the SAME battery `exit_policy_beats_null_2026_08_23.py` already implements (G1–G8), pointed at the new backfilled columns instead of the dead `cf_*` schema. Reuse that runner's battery functions; do not re-implement G1–G8 a second time.
4. **Multi-leg exit attribution**: of the 124 multi-leg positions, does the realized blended P&L (TP1 partial + runner) beat EITHER pure-null shape (`no_stop_ride`, `hold_to_time`) on the SAME positions where a single-leg exit does not — i.e., does scaling out itself carry value independent of stop placement? (New question, made askable only because this backfill is position-level; explicitly out of scope for run 1, listed here so it isn't lost.)

**Explicitly NOT a question this backfill answers:** any sizing/dollar-cap question (that is `LOSS-MAGNITUDE-AND-SIZING-IS-THE-UNTESTED-AXIS`, a separate frozen prereg per its own queue item) and any entry-selection question (exhausted per the same parent doc, §5f).

## 7. Forward clock

Carried forward from the original prereg unchanged (parent doc §5e): **do not re-cut this population. Re-adjudicate at +50 round trips or 2026-10-01, whichever comes first** — applies to the eventual beats-null re-ask (§6.1), not to the backfill build itself (the backfill is a one-time data-completeness fix, not a forward-accruing measurement).

## 8. `build_step` — the script this prereg requires, which does NOT exist yet

**No code has been written for this prereg.** The file below does not exist on disk as of this freeze (verified: no match for its name anywhere in the repo this session). It is named here, before being built, per this repo's freeze-before-runner discipline (same shape as `entry-quality-admissibility-prereg-2026-08-06.json`'s `commit_discipline` field).

```json
{
  "build_step": {
    "file": "backtest/tools/exit_counterfactual_backfill_2026_09_03.py",
    "symbol": "backfill_cf_counterfactuals",
    "must_contain": [
      "imports and reuses backtest.tools.exit_shape_parity_study.reconstruct_positions for position construction -- does NOT re-implement fill-to-position matching",
      "imports and reuses backtest.tools.exit_shape_parity_study.fetch_option_bars (or setup.scripts.trade_autopsy.fetch_bars_cached for on-disk caching) for OPRA bars -- NO synthetic pricing path, matching this repo's zero-synthetic convention",
      "imports and reuses setup.scripts.pain_ledger.holding_window for the entry+1 windowing convention -- does NOT re-derive entry+1",
      "imports and reuses setup.scripts.pain_ledger.recover_stop_mode_from_exit_trace and/or reads analysis/pain-ledger/mae-mfe.json's precomputed stop.stop_mode field keyed on (arm, symbol, date_et) -- does NOT reimplement stop_mode recovery, does NOT call trade_autopsy.lookup_stop_mode as the primary source (documented low-coverage limitation, section 4 above)",
      "computes cf_time_stop_pnl as the TRUE unmanaged null: hold from entry+1 to the 15:50 ET hard time-stop bar with premium_stop_pct ABSENT (not defaulted, not widened, not the existing -0.95 hold_to_time oracle shape) -- explicitly must NOT reuse trade_autopsy.COUNTERFACTUALS['hold_to_time'] or ['wide_stop_-50'] unchanged; define a new shape (e.g. 'true_unmanaged_hold') with no premium_stop_pct key evaluated at all",
      "computes cf_high_water_pnl as the position's best attainable exit within its own OPRA-observed excursion window, using the same excursion_metrics convention as setup/scripts/pain_ledger.py (first_extremes/excursion_metrics) -- does NOT re-derive MFE a second way",
      "writes an output ledger (NOT an in-place edit of journal/trades.csv's dead columns -- those writers stay untouched by this backfill; a new output file is the deliverable) that carries per position: arm, symbol, date_et, n_exit_legs (>1 flags a multi-leg position), realized_pnl, cf_time_stop_pnl, cf_high_water_pnl, stop_mode, stop_mode_source",
      "computes and reports G8-style coverage (usable cf_time_stop_pnl AND resolved stop_mode / total in-window positions) and REFUSES to print or write any beats-null/G6/G2/G3/G5 result when coverage < 80% -- coverage gate enforced in code, not left to the reader",
      "excludes-and-counts (never silently drops) positions with no OPRA bars, no exit-eligible bars, or non-positive entry price, mirroring analysis/pain-ledger/mae-mfe.json's n_no_bars/n_no_window/n_bad_entry disclosure fields",
      "$0 cost -- real Alpaca OPRA 1-min bars only, cached, same as every other position-level backfill in this repo; no new paid data source"
    ]
  }
}
```

## 9. Falsification note

The honest way this prereg dies without a beats-null answer ever being reached: coverage never clears 80% (e.g. OPRA cache gaps on the in-window dates, same failure mode that excluded 3 positions from `mae-mfe.json`'s own run). That would mean the data-completeness question this file exists to answer is ALSO unresolvable by construction on the current OPRA cache — a different, narrower failure than the original `cf_*` schema being dead code, and worth its own queue item if it happens, not a silent downgrade of the 80% bar.
