# STRATEGY-REGISTRY-DESIGN — one strategy menu for engine + promoter

> Design only (2026-07-01, follows [PIPELINE-AUDIT-2026-07-01](../audits/PIPELINE-AUDIT-2026-07-01.md) "Three disjoint hardcoded strategy menus… adding any new family = hand-editing code"). No refactor tonight — migration in small guarded steps below.

## Problem

The rig has **three disjoint hardcoded strategy menus**, so "wire a new validated family" means hand-editing code in three places (and the promoter can't do it at all — audit break #2):

| # | Menu | Location | Shape | Consumer |
|---|------|----------|-------|----------|
| 1 | Core-setup literals | `backtest/lib/engine/engine_cli.py:593-594` | inline strings `BEARISH_REJECTION_RIDE_THE_RIBBON` / `BULLISH_RECLAIM_RIDE_THE_RIBBON` | engine verdict `setup_name` |
| 2 | Extra-setup roster | `setup/scripts/setup_dispatch.py` `SetupDispatcher.run()` | 5 tuples `(setup_name, enable_flag_key, dispatch_method)` | heartbeat_core extra-signal path |
| 3 | Fleet registry | `automation/state/fleet/strategies.py:82` | `REGISTRY = (RIBBON_RIDE, VWAP_CONTINUATION)` — `Strategy(name, entry_setups, ExitShape)` | fleet arms' entry match + exit shape |

Consequences: the promoter had no machine-readable answer to "is this watcher executable?" (tonight's fix regex-parses menu #2's source — works, but is a stopgap); fleet exits and dispatcher flags drift independently (C29: exit knobs don't transfer across tiers); params carries dead keys nothing reads (C14); the arms-are-risk-profiles doctrine (every arm picks from the SAME menu) is enforced by convention, not structure.

## Design

**One canonical registry file: `automation/state/strategy-registry.json`** (data, not code — the promoter must be able to READ it and future tooling to APPEND to it without editing Python; same pattern as `params.json`, atomic-write, git-tracked).

```json
{
  "version": 1,
  "strategies": {
    "vwap_continuation": {
      "kind": "extra_setup",                       // "core" | "extra_setup"
      "entry_setups": ["VWAP_CONTINUATION", "vwap_continuation"],
      "enable_flag_key": "j_vwap_cont_enabled",    // the WATCH switch in params.json
      "detector": "backtest.lib.watchers.vwap_continuation_watcher:detect_vwap_continuation_setup",
      "exit_shape": {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.3,
                      "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"},
      "evidence": "analysis/recommendations/edgehunt-vwap_continuation.json",
      "status": "validated"                        // proposed|validated|retired
    },
    "ribbon_ride": { "kind": "core", "entry_setups": ["BEARISH_REJECTION_RIDE_THE_RIBBON",
      "BULLISH_RECLAIM_RIDE_THE_RIBBON"], "detector": null, "...": "core path, no dispatcher" }
  }
}
```

**Key decisions**

1. **Registry = capability menu ONLY. Params = per-account switches ONLY.** The registry says *what exists and how to reach it* (entry_setups, detector import path, flag key, validated exit shape, evidence). `params.json` / `aggressive/params.json` keep the per-account `<flag>_enabled` + `extra_setup_exec_armed` switches. This preserves the arms-are-risk-profiles doctrine structurally: one menu, N risk configs.
2. **A tiny read-only accessor module** `backtest/lib/engine/strategy_registry.py` — `load()`, `roster()` (name→flag), `by_setup(setup_name)`, `exit_shape(name)` — is the ONLY code that parses the JSON. All three consumers migrate to it; nothing else reads the file directly.
3. **Promoter writes `status` transitions, never structure.** `pipeline_promoter` on gates-pass: watcher in registry → flip params flag (today's behavior); not in registry → still a WIRE-DETECTOR proposal, whose ACCEPTANCE adds the registry entry. Adding an entry stays a reviewed code-adjacent change (rail-4), because a registry entry names a detector import path = code execution.
4. **Detector import paths are the contract.** `setup_dispatch` becomes a generic loop: for each registry entry with `kind=extra_setup` and flag ON, import `detector`, call it, wrap errors — deleting the five hand-written `_dispatch_*` methods. Fail-closed per entry (import error → `SKIP_IMPORT_ERROR`, exactly like today).

## Migration plan (small guarded steps, each independently shippable + revertible)

1. **M1 — write the registry file + accessor + reconciliation guard.** Generate `strategy-registry.json` from the three existing menus. Guard `test_strategy_registry_reconciles`: registry ⊇ setup_dispatch roster (names+flags), ⊇ fleet REGISTRY (names+entry_setups+exit shapes), ⊇ engine_cli literals. Nothing consumes it yet — pure additive, zero behavior change.
2. **M2 — promoter reads the registry** instead of regex-parsing setup_dispatch source (swap `read_dispatcher_roster` internals; contract guards in `test_pipeline_promoter_contract.py` already pin behavior). Fallback to source-parse if the file is missing (fail-open for the promoter, fail-closed for params writes).
3. **M3 — fleet reads the registry.** `strategies.py` builds `REGISTRY` from the accessor; `test_strategies.py` + the shared-signal guards pin equivalence. Ship only with a byte-identical `fired()`/`by_name()` behavior test.
4. **M4 — setup_dispatch reads the registry** (generic detector loop replaces the 5 tuples). The riskiest step: gate behind a params flag `use_strategy_registry_dispatch` defaulting false, A/B one full paper session of ledger rows byte-equal, then flip + remove the legacy tuples.
5. **M5 — engine_cli literals** become `by_setup()` lookups. Lowest value (2 strings), do last or not at all if churn-risk outweighs.

Each step: guard test first, after-hours ship, git-revert path stated in the commit. Never during 09:30–15:55 ET; M3/M4 touch files a sibling agent owns tonight — sequence after that work lands.

## Non-goals

- No auto-adding strategies to the registry from research output (wiring stays human/conductor-reviewed — rail-4).
- No per-arm strategy subsets (arms differ ONLY by risk profile — J's standing correction).
- No YAML/DB/new deps — one JSON + one stdlib accessor.
