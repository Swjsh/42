# September tune candidates — counterfactual A/B (2026-08-27)

**Scope:** OP-11 eval-first gate, ANALYSIS ONLY. Nothing in `params*.json`/`heartbeat*`/`strategies.py` was touched by
this pass. Population = engine-attribution option round trips, broker-truth `automation/state/fills-ledger.jsonl`
joined to entry context via `core-decisions.jsonl` (`exec.broker.id`) and fleet `decisions.jsonl`
(`placement.broker.id`), **2026-07-01 → 2026-08-27** (full window, not August-only — n=246 engine round trips,
225 context-matched). All 4 rules condition **only on entry-time information** (setup name, entry cost, ribbon-at-
entry, entry clock time) — no look-ahead.

IS = 2026-07-01..2026-08-14 · OOS = 2026-08-17..2026-08-27 (8 trading sessions — short OOS window, treat WF-proxy
numbers accordingly). Auto-ratify per OP-16/OP-11 gate ladder: `OOS_positive AND WF-proxy(OOS_delta/IS_delta)>=0.70
AND sub_window_stable(>=50% of ACTIVE weeks helped) AND anchor_no_regression`. `evidence_n>=15` is advisory only
(J is not a ratification gate; evidence_n<15 just means "don't oversell it").

## Summary table

| Rule | n blocked | Baseline pnl→CF pnl | Δ total | IS Δ | OOS Δ | Gates passed | Auto-ratify eligible | Enforcement point |
|---|---|---|---|---|---|---|---|---|
| `vwap_family_demotion` | 17 | $377→$1,673 | **+$1,296** | +$1,096 | +$200 | OOS+ ✓ / WF ✗ (0.182) / stable — / anchor ✓ | **NO** | `setup/scripts/heartbeat_core.py:3096-3102` (`extra_setup_exec_armed[setup_name]`, flip to hard-False) |
| `premium_cost_cap_1200` | 20 | $377→$2,831 | **+$2,454** | +$2,275 | +$179 | OOS+ ✓ / WF ✗ (0.079) / anchor ✓ | **NO** | `backtest/lib/risk_gate.py:365 check_order()` + `automation/state/params.json:64/247` (`max_premium_per_contract`, `v15_max_premium_pct_of_account`) |
| `mixed_ribbon_gate` | 7 (core only) | $core→ | **+$456** | +$92 | +$364 | OOS+ ✓ / WF ✓ (3.96) / stable ✓ (3/4 wk) / anchor ✓ | **YES on hard gates, but n=7 — SMALL SAMPLE, do not ship on this evidence alone** | `setup/scripts/heartbeat_core.py:1728` (ribbon_stack available at entry); **fleet arms have NO ribbon field — unenforceable there today** |
| `lunch_window_gate_1200_1300` | 24 | $377→$1,795 | +$1,418 | +$1,628 | **−$210** | OOS+ ✗ / WF ✗ (−0.129) / **removes an anchor-cohort winner** | **NO** | mirror `SKIP_BULL_1100_1200` at `orchestrator.py:1209-1210` / `heartbeat.md:540-545`, new `params.json` boolean + `dt.time(12,0)<=t<dt.time(13,0)` |

Full detail (per-trade blocked lists, weekly breakdown, IS/OOS split, anchor cohort check) in each rule's own JSON:
`analysis/recommendations/vwap_family_demotion.json`, `premium_cost_cap_1200.json`, `mixed_ribbon_gate.json`,
`lunch_window_gate_1200_1300.json`. Overlap matrix: `SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json`.

## Verdict

**None of the 4 clears the hard gate ladder cleanly for auto-ship.** All 4 show a positive full-window Δ, but that's
expected — every one of these rules simply removes trades from a population that's net-negative baseline ($377 over
246 trades). The question the gates ask is whether the removal is *directionally consistent forward*, not whether it
helped in the (much longer) IS window where it was mined.

- **`vwap_family_demotion`** and **`premium_cost_cap_1200`** both look attractive on raw delta (+$1,296 / +$2,454)
  but **fail WF-proxy hard** (0.18 / 0.08) — almost all the benefit is IS-concentrated (W32/W33, early-to-mid
  August), OOS barely moves. **Heavy overlap: 11 of 17 vwap-family blocks are ALSO >$1,200-cost trades** (65% of
  rule 1's population is a subset of rule 2's). Marginal value of `premium_cost_cap_1200` *after* `vwap_family_demotion`
  is already applied: only 9 additional trades, +$1,185 marginal delta, **still fails gates** (see overlap JSON) —
  most of rule 2's apparent edge is really rule 1's edge wearing a cost-cap costume.
- **`mixed_ribbon_gate`** is the only one that clears every hard gate (OOS+, WF 3.96, 3/4 active weeks help, anchor
  clean) — but on **n=7 blocked trades total across the full 8-week window**. That is a single-digit-trade result;
  the 3.96 WF-proxy ratio is an artifact of a tiny IS_delta ($92) denominator, not evidence of a robust edge. Also
  **fleet arms (155 of the 246 engine trades) have no ribbon field at entry — this rule is literally unenforceable
  there today**, so even if shipped it only touches core (safe-2/bold-2).
- **`lunch_window_gate_1200_1300`** is the clearest NO: OOS delta is *negative* (−$210, engine got WORSE forward),
  and it **removes a ribbon_ride/chart-stop anchor-cohort winner** — the one hard "never do this" signal in the
  battery.

**Bottom line: hold all 4 in shadow, ship none.** The honest read of this window is that VWAP-family demotion and
the premium cap are the same overfit IS-August story told twice (overlap-confirmed), the ribbon-mixed gate is too
thin to trust (n=7), and the lunch-window gate actively regresses OOS and hits the anchor. Re-run this scorecard
once OOS accrues past 15 sessions (currently 8) before revisiting.

## Enforcement points (read-only recon, no edits made)

1. **Setup blocking** — `automation/state/params.json` already has a per-setup allow-flag mechanism:
   `extra_setup_exec_armed[setup_name]` read at `setup/scripts/heartbeat_core.py:3096-3102` (doc block
   `:3038-3048`). `setup_name` resolved at `heartbeat_core.py:2628`, before order placement at `:2898-2902`.
   Backtest side (`backtest/lib/filters.py`) has NO existing block-list — would need a new check inside
   `evaluate_bearish_setup`/`evaluate_bullish_setup` (lines 1535/1246) or `backtest/lib/engine/gates.py` to keep
   live/backtest parity (gamma-sync doctrine). Fleet-side: `automation/state/fleet/strategies.py:202,280`.
2. **Premium/entry-cost cap — ALREADY LIVE, not a new knob.** `params.json:64` `max_premium_per_contract: 3.3`
   (per-share) and `:247-253` `v15_max_premium_pct_of_account` (equity-tiered). Both enforced through the single
   shared `check_order()` at `backtest/lib/risk_gate.py:365` (`CODE_MAX_PREMIUM_TIER` at `:133`, applied `:630`),
   called from both live (`automation/scripts/pre_order_gate.py:54`) and backtest — no drift risk. A $1,200 flat
   cap would extend this same function/table, not create a parallel path.
3. **Ribbon-at-entry** — computed via `automation/scripts/ribbon_cli.py`, read at `heartbeat.md:225-247`
   (TV-then-Alpaca fallback `:131-140`), consumed at `heartbeat_core.py:1222,1242,1728`. **Core arms only** —
   fleet arms (`strategies.py`/`entry_manager.py`/`build_shared_signal.py`) carry no live ribbon read of their own;
   they consume a shared-signal JSON derived from the core tick, not an independent ribbon computation.
4. **Time-window gate** — production precedent is `block_bull_1100_1200` at `orchestrator.py:1209-1210` (doctrine:
   `heartbeat.md:540-545`, "Gate H"): boolean `params.json` flag + `dt.time(11,0)<=bar_time<dt.time(12,0)` check,
   side-restricted to BULL. A symmetric 12:00-13:00 block would follow the identical shape.
